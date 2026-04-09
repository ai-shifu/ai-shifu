"""Serialization helpers and shared billing value normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import Flask
from sqlalchemy import case

from flaskr.dao import db
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
    BILL_USAGE_TYPE_LLM,
    BILL_USAGE_TYPE_TTS,
)
from flaskr.util.timezone import serialize_with_app_timezone

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
    BILLING_RENEWAL_EVENT_STATUS_FAILED,
    BILLING_RENEWAL_EVENT_STATUS_LABELS,
    BILLING_RENEWAL_EVENT_STATUS_PENDING,
    BILLING_RENEWAL_EVENT_STATUS_PROCESSING,
    BILLING_RENEWAL_EVENT_TYPE_LABELS,
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_CANCELED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED,
    BILLING_SUBSCRIPTION_STATUS_LABELS,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    CREDIT_BUCKET_CATEGORY_LABELS,
    CREDIT_BUCKET_STATUS_LABELS,
    CREDIT_LEDGER_ENTRY_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_LABELS,
)
from .models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingDomainBinding,
    BillingEntitlement,
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
    BillingPlanDTO,
    BillingRenewalEventDTO,
    BillingSubscriptionDTO,
    BillingTopupProductDTO,
    BillingWalletBucketDTO,
    BillingWalletSnapshotDTO,
)
from .value_objects import (
    JsonObjectMap,
    ProductCodeIndex,
    RenewalEventIndex,
    WalletIndex,
)

_USAGE_SCENE_LABELS = {
    BILL_USAGE_SCENE_DEBUG: "debug",
    BILL_USAGE_SCENE_PREVIEW: "preview",
    BILL_USAGE_SCENE_PROD: "production",
}

_USAGE_TYPE_LABELS = {
    BILL_USAGE_TYPE_LLM: "llm",
    BILL_USAGE_TYPE_TTS: "tts",
}

_ACTIVE_SUBSCRIPTION_STATUSES = (
    BILLING_SUBSCRIPTION_STATUS_ACTIVE,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_DRAFT,
)

_SUBSCRIPTION_STATUS_SORT = {
    BILLING_SUBSCRIPTION_STATUS_ACTIVE: 1,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE: 2,
    BILLING_SUBSCRIPTION_STATUS_PAUSED: 3,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED: 4,
    BILLING_SUBSCRIPTION_STATUS_DRAFT: 5,
    BILLING_SUBSCRIPTION_STATUS_CANCELED: 6,
    BILLING_SUBSCRIPTION_STATUS_EXPIRED: 7,
}


def _normalize_bid(value: Any) -> str:
    return str(value or "").strip()


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _decimal_to_number(value: Any) -> int | float:
    if value is None:
        return 0
    if isinstance(value, Decimal):
        if value == value.to_integral():
            return int(value)
        return float(value)
    if isinstance(value, (int, float)):
        return value
    try:
        normalized = Decimal(str(value))
    except Exception:
        return 0
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(normalized)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_to_number(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, JsonObjectMap):
        payload = JsonObjectMap(
            values={
                str(key): _normalize_json_value(item) for key, item in value.items()
            }
        )
        usage_scene = payload.get("usage_scene")
        if isinstance(usage_scene, (int, str)):
            payload["usage_scene"] = _USAGE_SCENE_LABELS.get(
                _safe_int(usage_scene),
                str(usage_scene),
            )
        return payload
    if isinstance(value, dict):
        payload = JsonObjectMap(
            values={
                str(key): _normalize_json_value(item) for key, item in value.items()
            }
        )
        usage_scene = payload.get("usage_scene")
        if isinstance(usage_scene, (int, str)):
            payload["usage_scene"] = _USAGE_SCENE_LABELS.get(
                _safe_int(usage_scene),
                str(usage_scene),
            )
        return payload
    return value


def _normalize_json_object(value: Any) -> JsonObjectMap:
    normalized = _normalize_json_value(value)
    if isinstance(normalized, JsonObjectMap):
        return normalized
    return JsonObjectMap()


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _safe_to_decimal(value: Any, *, default: Any) -> Decimal:
    try:
        return _to_decimal(value)
    except Exception:
        return _to_decimal(default)


def _safe_to_positive_int(value: Any, *, default: int) -> int:
    candidate = _safe_int(value)
    if candidate is None or candidate <= 0:
        return default
    return candidate


def _parse_config_datetime(value: Any) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text))
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _serialize_dt(
    app: Flask,
    value: datetime | None,
    *,
    timezone_name: str | None = None,
) -> str | None:
    return serialize_with_app_timezone(app, value, timezone_name)


def _serialize_product(row: BillingProduct) -> BillingPlanDTO | BillingTopupProductDTO:
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
        "credit_amount": _decimal_to_number(row.credit_amount),
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
            "month",
        )
        payload["billing_interval_count"] = int(row.billing_interval_count or 0)
        payload["auto_renew_enabled"] = bool(row.auto_renew_enabled)
        return BillingPlanDTO(**payload)
    return BillingTopupProductDTO(**payload)


def _serialize_wallet(wallet: CreditWallet | None) -> BillingWalletSnapshotDTO:
    if wallet is None:
        return BillingWalletSnapshotDTO(
            available_credits=0,
            reserved_credits=0,
            lifetime_granted_credits=0,
            lifetime_consumed_credits=0,
        )
    return BillingWalletSnapshotDTO(
        available_credits=_decimal_to_number(wallet.available_credits),
        reserved_credits=_decimal_to_number(wallet.reserved_credits),
        lifetime_granted_credits=_decimal_to_number(wallet.lifetime_granted_credits),
        lifetime_consumed_credits=_decimal_to_number(wallet.lifetime_consumed_credits),
    )


def _load_current_subscription(creator_bid: str) -> BillingSubscription | None:
    prioritized = (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
            BillingSubscription.status.in_(_ACTIVE_SUBSCRIPTION_STATUSES),
        )
        .order_by(
            case(
                *[
                    (BillingSubscription.status == status, rank)
                    for status, rank in _SUBSCRIPTION_STATUS_SORT.items()
                ],
                else_=99,
            ),
            BillingSubscription.current_period_end_at.desc(),
            BillingSubscription.created_at.desc(),
            BillingSubscription.id.desc(),
        )
        .first()
    )
    if prioritized is not None:
        return prioritized
    return (
        BillingSubscription.query.filter(
            BillingSubscription.deleted == 0,
            BillingSubscription.creator_bid == creator_bid,
        )
        .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id.desc())
        .first()
    )


def _load_product_code_map(product_bids: list[str]) -> ProductCodeIndex:
    normalized_bids = [bid for bid in product_bids if bid]
    if not normalized_bids:
        return ProductCodeIndex()
    rows = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid.in_(normalized_bids),
        )
        .order_by(BillingProduct.id.desc())
        .all()
    )
    return ProductCodeIndex(
        values={row.product_bid: row.product_code for row in rows},
    )


def _load_wallet_map(creator_bids: list[str]) -> WalletIndex:
    normalized_creator_bids = [_normalize_bid(bid) for bid in creator_bids if bid]
    if not normalized_creator_bids:
        return WalletIndex()
    rows = (
        CreditWallet.query.filter(
            CreditWallet.deleted == 0,
            CreditWallet.creator_bid.in_(normalized_creator_bids),
        )
        .order_by(CreditWallet.creator_bid.asc(), CreditWallet.id.desc())
        .all()
    )
    payload: dict[str, CreditWallet] = {}
    for row in rows:
        payload.setdefault(row.creator_bid, row)
    return WalletIndex(values=payload)


def _load_latest_renewal_event_map(
    subscription_bids: list[str],
) -> RenewalEventIndex:
    normalized_subscription_bids = [
        _normalize_bid(bid) for bid in subscription_bids if bid
    ]
    if not normalized_subscription_bids:
        return RenewalEventIndex()
    rows = (
        BillingRenewalEvent.query.filter(
            BillingRenewalEvent.deleted == 0,
            BillingRenewalEvent.subscription_bid.in_(normalized_subscription_bids),
        )
        .order_by(
            BillingRenewalEvent.subscription_bid.asc(),
            BillingRenewalEvent.scheduled_at.desc(),
            BillingRenewalEvent.id.desc(),
        )
        .all()
    )
    payload: dict[str, BillingRenewalEvent] = {}
    for row in rows:
        payload.setdefault(row.subscription_bid, row)
    return RenewalEventIndex(values=payload)


def _load_admin_creator_bids(*, creator_bid: str = "") -> list[str]:
    normalized_creator_bid = _normalize_bid(creator_bid)
    if normalized_creator_bid:
        return [normalized_creator_bid]

    creator_bids: set[str] = set()
    creator_columns = (
        (BillingEntitlement, BillingEntitlement.creator_bid),
        (BillingSubscription, BillingSubscription.creator_bid),
        (BillingOrder, BillingOrder.creator_bid),
        (BillingDomainBinding, BillingDomainBinding.creator_bid),
        (CreditWallet, CreditWallet.creator_bid),
        (BillingDailyUsageMetric, BillingDailyUsageMetric.creator_bid),
        (BillingDailyLedgerSummary, BillingDailyLedgerSummary.creator_bid),
    )
    for model, column in creator_columns:
        rows = (
            db.session.query(column)
            .filter(model.deleted == 0, column != "")
            .distinct()
            .all()
        )
        creator_bids.update(
            normalized
            for normalized in (_normalize_bid(row[0]) for row in rows)
            if normalized
        )
    return sorted(creator_bids)


def _serialize_subscription(
    app: Flask,
    row: BillingSubscription | None,
    *,
    timezone_name: str | None = None,
) -> BillingSubscriptionDTO | None:
    if row is None:
        return None
    product_codes = _load_product_code_map([row.product_bid])
    next_product_bid = _normalize_bid(row.next_product_bid)
    return BillingSubscriptionDTO(
        subscription_bid=row.subscription_bid,
        product_bid=row.product_bid,
        product_code=product_codes.get(row.product_bid, ""),
        status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(row.status, "draft"),
        billing_provider=str(row.billing_provider or ""),
        current_period_start_at=_serialize_dt(
            app,
            row.current_period_start_at,
            timezone_name=timezone_name,
        ),
        current_period_end_at=_serialize_dt(
            app,
            row.current_period_end_at,
            timezone_name=timezone_name,
        ),
        grace_period_end_at=_serialize_dt(
            app,
            row.grace_period_end_at,
            timezone_name=timezone_name,
        ),
        cancel_at_period_end=bool(row.cancel_at_period_end),
        next_product_bid=next_product_bid or None,
        last_renewed_at=_serialize_dt(
            app,
            row.last_renewed_at,
            timezone_name=timezone_name,
        ),
        last_failed_at=_serialize_dt(
            app,
            row.last_failed_at,
            timezone_name=timezone_name,
        ),
    )


def _serialize_admin_subscription(
    app: Flask,
    row: BillingSubscription,
    *,
    product_codes: ProductCodeIndex,
    wallet: CreditWallet | None,
    renewal_event: BillingRenewalEvent | None,
    timezone_name: str | None = None,
) -> AdminBillingSubscriptionDTO:
    next_product_bid = _normalize_bid(row.next_product_bid)
    return AdminBillingSubscriptionDTO(
        subscription_bid=row.subscription_bid,
        creator_bid=row.creator_bid,
        product_bid=row.product_bid,
        product_code=product_codes.get(row.product_bid, ""),
        status=BILLING_SUBSCRIPTION_STATUS_LABELS.get(row.status, "draft"),
        billing_provider=str(row.billing_provider or ""),
        current_period_start_at=_serialize_dt(
            app,
            row.current_period_start_at,
            timezone_name=timezone_name,
        ),
        current_period_end_at=_serialize_dt(
            app,
            row.current_period_end_at,
            timezone_name=timezone_name,
        ),
        grace_period_end_at=_serialize_dt(
            app,
            row.grace_period_end_at,
            timezone_name=timezone_name,
        ),
        cancel_at_period_end=bool(row.cancel_at_period_end),
        next_product_bid=next_product_bid or None,
        next_product_code=product_codes.get(next_product_bid, "")
        if next_product_bid
        else "",
        last_renewed_at=_serialize_dt(
            app,
            row.last_renewed_at,
            timezone_name=timezone_name,
        ),
        last_failed_at=_serialize_dt(
            app,
            row.last_failed_at,
            timezone_name=timezone_name,
        ),
        wallet=_serialize_wallet(wallet),
        latest_renewal_event=_serialize_renewal_event(
            app,
            renewal_event,
            timezone_name=timezone_name,
        ),
        has_attention=_subscription_has_attention(
            row,
            renewal_event=renewal_event,
        ),
    )


def _serialize_renewal_event(
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
        scheduled_at=_serialize_dt(
            app,
            row.scheduled_at,
            timezone_name=timezone_name,
        ),
        processed_at=_serialize_dt(
            app,
            row.processed_at,
            timezone_name=timezone_name,
        ),
        attempt_count=int(row.attempt_count or 0),
        last_error=str(row.last_error or ""),
        payload=_normalize_json_object(row.payload_json).to_metadata_json(),
    )


def _build_billing_alerts(
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


def _serialize_wallet_bucket(
    app: Flask,
    row: CreditWalletBucket,
    *,
    timezone_name: str | None = None,
) -> BillingWalletBucketDTO:
    return BillingWalletBucketDTO(
        wallet_bucket_bid=row.wallet_bucket_bid,
        category=CREDIT_BUCKET_CATEGORY_LABELS.get(row.bucket_category, "free"),
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        source_bid=row.source_bid,
        available_credits=_decimal_to_number(row.available_credits),
        effective_from=_serialize_dt(
            app,
            row.effective_from,
            timezone_name=timezone_name,
        )
        or "",
        effective_to=_serialize_dt(
            app,
            row.effective_to,
            timezone_name=timezone_name,
        ),
        priority=int(row.priority or 0),
        status=CREDIT_BUCKET_STATUS_LABELS.get(row.status, "active"),
    )


def _serialize_ledger_entry(
    app: Flask,
    row: CreditLedgerEntry,
    *,
    timezone_name: str | None = None,
) -> BillingLedgerItemDTO:
    return BillingLedgerItemDTO(
        ledger_bid=row.ledger_bid,
        wallet_bucket_bid=row.wallet_bucket_bid,
        entry_type=CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant"),
        source_type=CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        source_bid=row.source_bid,
        idempotency_key=row.idempotency_key,
        amount=_decimal_to_number(row.amount),
        balance_after=_decimal_to_number(row.balance_after),
        expires_at=_serialize_dt(app, row.expires_at, timezone_name=timezone_name),
        consumable_from=_serialize_dt(
            app,
            row.consumable_from,
            timezone_name=timezone_name,
        ),
        metadata=_normalize_json_object(row.metadata_json).to_metadata_json(),
        created_at=_serialize_dt(app, row.created_at, timezone_name=timezone_name)
        or "",
    )


def _serialize_daily_usage_metric(
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
        consumed_credits=_decimal_to_number(row.consumed_credits),
        window_started_at=_serialize_dt(
            app,
            row.window_started_at,
            timezone_name=timezone_name,
        )
        or "",
        window_ended_at=_serialize_dt(
            app,
            row.window_ended_at,
            timezone_name=timezone_name,
        )
        or "",
    )


def _serialize_daily_ledger_summary(
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
        amount=_decimal_to_number(row.amount),
        entry_count=int(row.entry_count or 0),
        window_started_at=_serialize_dt(
            app,
            row.window_started_at,
            timezone_name=timezone_name,
        )
        or "",
        window_ended_at=_serialize_dt(
            app,
            row.window_ended_at,
            timezone_name=timezone_name,
        )
        or "",
    )


def _serialize_admin_entitlement_state(
    app: Flask,
    state,
    *,
    timezone_name: str | None = None,
) -> AdminBillingEntitlementDTO:
    return AdminBillingEntitlementDTO(
        creator_bid=_normalize_bid(state.creator_bid),
        source_kind=str(state.source_kind or "default"),
        source_type=str(state.source_type or ""),
        source_bid=_normalize_bid(state.source_bid) or None,
        product_bid=_normalize_bid(state.product_bid),
        branding_enabled=bool(state.branding_enabled),
        custom_domain_enabled=bool(state.custom_domain_enabled),
        priority_class=str(state.priority_class or "standard"),
        max_concurrency=max(int(state.max_concurrency or 1), 1),
        analytics_tier=str(state.analytics_tier or "basic"),
        support_tier=str(state.support_tier or "self_serve"),
        effective_from=_serialize_dt(
            app,
            state.effective_from,
            timezone_name=timezone_name,
        ),
        effective_to=_serialize_dt(
            app,
            state.effective_to,
            timezone_name=timezone_name,
        ),
        feature_payload=state.feature_payload.to_metadata_json(),
    )


def _serialize_admin_domain_binding(
    app: Flask,
    row: BillingDomainBinding,
    *,
    custom_domain_enabled: bool = False,
    timezone_name: str | None = None,
) -> AdminBillingDomainBindingDTO:
    metadata = _normalize_json_object(row.metadata_json)
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
        last_verified_at=_serialize_dt(
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


def _serialize_admin_daily_usage_metric(
    app: Flask,
    row: BillingDailyUsageMetric,
    *,
    timezone_name: str | None = None,
) -> AdminBillingDailyUsageMetricDTO:
    payload = _serialize_daily_usage_metric(
        app,
        row,
        timezone_name=timezone_name,
    )
    return AdminBillingDailyUsageMetricDTO(
        **payload.__json__(), creator_bid=row.creator_bid
    )


def _serialize_admin_daily_ledger_summary(
    app: Flask,
    row: BillingDailyLedgerSummary,
    *,
    timezone_name: str | None = None,
) -> AdminBillingDailyLedgerSummaryDTO:
    payload = _serialize_daily_ledger_summary(
        app,
        row,
        timezone_name=timezone_name,
    )
    return AdminBillingDailyLedgerSummaryDTO(
        **payload.__json__(),
        creator_bid=row.creator_bid,
    )


def _serialize_order_summary(
    app: Flask,
    row: BillingOrder,
    *,
    timezone_name: str | None = None,
) -> BillingOrderSummaryDTO:
    subscription_bid = _normalize_bid(row.subscription_bid)
    payment_mode = _resolve_billing_order_payment_mode(row)

    return BillingOrderSummaryDTO(
        billing_order_bid=row.billing_order_bid,
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
        created_at=_serialize_dt(app, row.created_at, timezone_name=timezone_name)
        or "",
        paid_at=_serialize_dt(app, row.paid_at, timezone_name=timezone_name),
    )


def _serialize_admin_order_summary(
    app: Flask,
    row: BillingOrder,
    *,
    timezone_name: str | None = None,
) -> AdminBillingOrderDTO:
    payload = _serialize_order_summary(app, row, timezone_name=timezone_name)
    return AdminBillingOrderDTO(
        **payload.__json__(),
        failure_code=str(row.failure_code or ""),
        failed_at=_serialize_dt(
            app,
            row.failed_at,
            timezone_name=timezone_name,
        ),
        refunded_at=_serialize_dt(
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


normalize_bid = _normalize_bid
to_decimal = _to_decimal
decimal_to_number = _decimal_to_number
normalize_json_value = _normalize_json_value
normalize_json_object = _normalize_json_object
safe_int = _safe_int
coerce_bool = _coerce_bool
safe_to_decimal = _safe_to_decimal
safe_to_positive_int = _safe_to_positive_int
parse_config_datetime = _parse_config_datetime
coerce_datetime = _coerce_datetime
serialize_dt = _serialize_dt
serialize_product = _serialize_product
serialize_wallet = _serialize_wallet
load_current_subscription = _load_current_subscription
load_product_code_map = _load_product_code_map
load_wallet_map = _load_wallet_map
load_latest_renewal_event_map = _load_latest_renewal_event_map
serialize_subscription = _serialize_subscription
serialize_admin_subscription = _serialize_admin_subscription
serialize_renewal_event = _serialize_renewal_event
build_billing_alerts = _build_billing_alerts
serialize_wallet_bucket = _serialize_wallet_bucket
serialize_ledger_entry = _serialize_ledger_entry
serialize_daily_usage_metric = _serialize_daily_usage_metric
serialize_daily_ledger_summary = _serialize_daily_ledger_summary
serialize_admin_entitlement_state = _serialize_admin_entitlement_state
serialize_admin_domain_binding = _serialize_admin_domain_binding
serialize_admin_daily_usage_metric = _serialize_admin_daily_usage_metric
serialize_admin_daily_ledger_summary = _serialize_admin_daily_ledger_summary
serialize_order_summary = _serialize_order_summary
serialize_admin_order_summary = _serialize_admin_order_summary
subscription_has_attention = _subscription_has_attention
