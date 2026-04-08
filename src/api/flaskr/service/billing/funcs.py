"""Read-model helpers for the creator billing service."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask
from sqlalchemy import case

from flaskr.service.common.models import raise_error
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.util.timezone import serialize_with_app_timezone

from .consts import (
    BILLING_INTERVAL_LABELS,
    BILLING_ORDER_STATUS_LABELS,
    BILLING_ORDER_TYPE_LABELS,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_LABELS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
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
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)

DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_USAGE_SCENE_LABELS = {
    BILL_USAGE_SCENE_DEBUG: "debug",
    BILL_USAGE_SCENE_PREVIEW: "preview",
    BILL_USAGE_SCENE_PROD: "production",
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


def build_billing_route_bootstrap(path_prefix: str) -> dict[str, Any]:
    """Return the billing route manifest defined by the design doc."""

    creator_routes = [
        {"method": "GET", "path": f"{path_prefix}/catalog"},
        {"method": "GET", "path": f"{path_prefix}/overview"},
        {"method": "GET", "path": f"{path_prefix}/wallet-buckets"},
        {"method": "GET", "path": f"{path_prefix}/ledger"},
        {"method": "GET", "path": f"{path_prefix}/orders"},
        {"method": "GET", "path": f"{path_prefix}/orders/{{billing_order_bid}}"},
        {
            "method": "POST",
            "path": f"{path_prefix}/orders/{{billing_order_bid}}/sync",
        },
        {"method": "POST", "path": f"{path_prefix}/subscriptions/checkout"},
        {"method": "POST", "path": f"{path_prefix}/subscriptions/cancel"},
        {"method": "POST", "path": f"{path_prefix}/subscriptions/resume"},
        {"method": "POST", "path": f"{path_prefix}/topups/checkout"},
        {"method": "POST", "path": f"{path_prefix}/webhooks/stripe"},
        {"method": "POST", "path": f"{path_prefix}/webhooks/pingxx"},
    ]
    admin_routes = [
        {"method": "GET", "path": "/api/admin/billing/subscriptions"},
        {"method": "GET", "path": "/api/admin/billing/orders"},
        {"method": "POST", "path": "/api/admin/billing/ledger/adjust"},
    ]
    return {
        "service": "billing",
        "status": "bootstrap",
        "path_prefix": path_prefix,
        "creator_routes": creator_routes,
        "admin_routes": admin_routes,
        "notes": [
            "Registered via plugin route loading from flaskr/service.",
            "Keeps creator billing separate from legacy /order tables and routes.",
            "Concrete schema, checkout, sync, webhook, and ledger behavior lands in later tasks.",
        ],
    }


def build_billing_catalog(app: Flask) -> dict[str, list[dict[str, Any]]]:
    """Return plan and topup catalog projections."""

    with app.app_context():
        rows = (
            BillingProduct.query.filter(
                BillingProduct.deleted == 0,
                BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
                BillingProduct.product_type.in_(
                    [BILLING_PRODUCT_TYPE_PLAN, BILLING_PRODUCT_TYPE_TOPUP]
                ),
            )
            .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
            .all()
        )

        plans: list[dict[str, Any]] = []
        topups: list[dict[str, Any]] = []
        for row in rows:
            payload = _serialize_product(row)
            if payload["product_type"] == "plan":
                plans.append(payload)
            elif payload["product_type"] == "topup":
                topups.append(payload)

        return {"plans": plans, "topups": topups}


def build_billing_overview(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return the wallet snapshot, current subscription, and alerts."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        wallet = (
            CreditWallet.query.filter(
                CreditWallet.deleted == 0,
                CreditWallet.creator_bid == normalized_creator_bid,
            )
            .order_by(CreditWallet.id.desc())
            .first()
        )
        subscription = _load_current_subscription(normalized_creator_bid)

        wallet_payload = _serialize_wallet(wallet)
        subscription_payload = _serialize_subscription(
            app, subscription, timezone_name=timezone_name
        )
        return {
            "creator_bid": normalized_creator_bid,
            "wallet": wallet_payload,
            "subscription": subscription_payload,
            "billing_alerts": _build_billing_alerts(wallet_payload, subscription),
        }


def build_billing_wallet_buckets(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> list[dict[str, Any]]:
    """Return wallet bucket projections sorted by actual consumption order."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        rows = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.creator_bid == normalized_creator_bid,
            )
            .order_by(
                CreditWalletBucket.priority.asc(),
                case((CreditWalletBucket.effective_to.is_(None), 1), else_=0).asc(),
                CreditWalletBucket.effective_to.asc(),
                CreditWalletBucket.created_at.asc(),
                CreditWalletBucket.id.asc(),
            )
            .all()
        )
        return [
            _serialize_wallet_bucket(app, row, timezone_name=timezone_name)
            for row in rows
        ]


def build_billing_ledger_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return paginated credit ledger entries for a creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    with app.app_context():
        query = CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == normalized_creator_bid,
        ).order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc())
        return _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_ledger_entry(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )


def build_billing_orders_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return paginated billing orders for a creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    with app.app_context():
        query = BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == normalized_creator_bid,
        ).order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc())
        return _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_order_summary(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )


def build_billing_order_detail(
    app: Flask,
    creator_bid: str,
    billing_order_bid: str,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    """Return a single billing order detail for the current creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(billing_order_bid)
    with app.app_context():
        row = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.creator_bid == normalized_creator_bid,
                BillingOrder.billing_order_bid == normalized_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if row is None:
            raise_error("server.order.orderNotFound")

        payload = _serialize_order_summary(app, row, timezone_name=timezone_name)
        payload["metadata"] = _normalize_json_value(row.metadata_json)
        payload["failure_code"] = str(row.failure_code or "")
        payload["refunded_at"] = _serialize_dt(
            app, row.refunded_at, timezone_name=timezone_name
        )
        payload["failed_at"] = _serialize_dt(
            app, row.failed_at, timezone_name=timezone_name
        )
        return payload


def normalize_pagination(page_index: int, page_size: int) -> tuple[int, int]:
    """Normalize list pagination parameters to the shared admin defaults."""

    try:
        safe_page_index = max(int(page_index or DEFAULT_PAGE_INDEX), 1)
    except (TypeError, ValueError):
        safe_page_index = DEFAULT_PAGE_INDEX
    try:
        safe_page_size = max(int(page_size or DEFAULT_PAGE_SIZE), 1)
    except (TypeError, ValueError):
        safe_page_size = DEFAULT_PAGE_SIZE
    return safe_page_index, min(safe_page_size, MAX_PAGE_SIZE)


def _normalize_bid(value: Any) -> str:
    return str(value or "").strip()


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
    if isinstance(value, dict):
        payload = {str(key): _normalize_json_value(item) for key, item in value.items()}
        usage_scene = payload.get("usage_scene")
        if isinstance(usage_scene, (int, str)):
            payload["usage_scene"] = _USAGE_SCENE_LABELS.get(
                _safe_int(usage_scene),
                str(usage_scene),
            )
        return payload
    return value


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _serialize_dt(
    app: Flask,
    value: datetime | None,
    *,
    timezone_name: str | None = None,
) -> str | None:
    return serialize_with_app_timezone(app, value, timezone_name)


def _serialize_product(row: BillingProduct) -> dict[str, Any]:
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
        payload["status_badge_key"] = f"module.billing.catalog.badges.{badge}"
    if row.product_type == BILLING_PRODUCT_TYPE_PLAN:
        payload["billing_interval"] = BILLING_INTERVAL_LABELS.get(
            row.billing_interval,
            "month",
        )
        payload["billing_interval_count"] = int(row.billing_interval_count or 0)
        payload["auto_renew_enabled"] = bool(row.auto_renew_enabled)
    return payload


def _serialize_wallet(wallet: CreditWallet | None) -> dict[str, Any]:
    if wallet is None:
        return {
            "available_credits": 0,
            "reserved_credits": 0,
            "lifetime_granted_credits": 0,
            "lifetime_consumed_credits": 0,
        }
    return {
        "available_credits": _decimal_to_number(wallet.available_credits),
        "reserved_credits": _decimal_to_number(wallet.reserved_credits),
        "lifetime_granted_credits": _decimal_to_number(wallet.lifetime_granted_credits),
        "lifetime_consumed_credits": _decimal_to_number(
            wallet.lifetime_consumed_credits
        ),
    }


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


def _load_product_code_map(product_bids: list[str]) -> dict[str, str]:
    normalized_bids = [bid for bid in product_bids if bid]
    if not normalized_bids:
        return {}
    rows = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.product_bid.in_(normalized_bids),
        )
        .order_by(BillingProduct.id.desc())
        .all()
    )
    return {row.product_bid: row.product_code for row in rows}


def _serialize_subscription(
    app: Flask,
    row: BillingSubscription | None,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    product_codes = _load_product_code_map([row.product_bid])
    next_product_bid = _normalize_bid(row.next_product_bid)
    return {
        "subscription_bid": row.subscription_bid,
        "product_bid": row.product_bid,
        "product_code": product_codes.get(row.product_bid, ""),
        "status": BILLING_SUBSCRIPTION_STATUS_LABELS.get(row.status, "draft"),
        "billing_provider": str(row.billing_provider or ""),
        "current_period_start_at": _serialize_dt(
            app,
            row.current_period_start_at,
            timezone_name=timezone_name,
        ),
        "current_period_end_at": _serialize_dt(
            app,
            row.current_period_end_at,
            timezone_name=timezone_name,
        ),
        "grace_period_end_at": _serialize_dt(
            app,
            row.grace_period_end_at,
            timezone_name=timezone_name,
        ),
        "cancel_at_period_end": bool(row.cancel_at_period_end),
        "next_product_bid": next_product_bid or None,
        "last_renewed_at": _serialize_dt(
            app,
            row.last_renewed_at,
            timezone_name=timezone_name,
        ),
        "last_failed_at": _serialize_dt(
            app,
            row.last_failed_at,
            timezone_name=timezone_name,
        ),
    }


def _build_billing_alerts(
    wallet_payload: dict[str, Any],
    subscription: BillingSubscription | None,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    available_credits = float(wallet_payload.get("available_credits") or 0)

    if available_credits <= 0:
        alerts.append(
            {
                "code": "low_balance",
                "severity": "warning",
                "message_key": "module.billing.alerts.lowBalance",
                "message_params": {
                    "available_credits": wallet_payload.get("available_credits", 0)
                },
                "action_type": "checkout_topup",
                "action_payload": {},
            }
        )

    if subscription is None:
        return alerts

    if subscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE:
        alerts.append(
            {
                "code": "subscription_past_due",
                "severity": "error",
                "message_key": "module.billing.alerts.subscriptionPastDue",
                "action_type": "open_orders",
                "action_payload": {
                    "subscription_bid": subscription.subscription_bid,
                },
            }
        )

    if subscription.cancel_at_period_end:
        alerts.append(
            {
                "code": "subscription_cancel_scheduled",
                "severity": "info",
                "message_key": "module.billing.alerts.cancelScheduled",
                "action_type": "resume_subscription",
                "action_payload": {
                    "subscription_bid": subscription.subscription_bid,
                },
            }
        )

    return alerts


def _serialize_wallet_bucket(
    app: Flask,
    row: CreditWalletBucket,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    return {
        "wallet_bucket_bid": row.wallet_bucket_bid,
        "category": CREDIT_BUCKET_CATEGORY_LABELS.get(row.bucket_category, "free"),
        "source_type": CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        "source_bid": row.source_bid,
        "available_credits": _decimal_to_number(row.available_credits),
        "effective_from": _serialize_dt(
            app,
            row.effective_from,
            timezone_name=timezone_name,
        )
        or "",
        "effective_to": _serialize_dt(
            app,
            row.effective_to,
            timezone_name=timezone_name,
        ),
        "priority": int(row.priority or 0),
        "status": CREDIT_BUCKET_STATUS_LABELS.get(row.status, "active"),
    }


def _serialize_ledger_entry(
    app: Flask,
    row: CreditLedgerEntry,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    return {
        "ledger_bid": row.ledger_bid,
        "wallet_bucket_bid": row.wallet_bucket_bid,
        "entry_type": CREDIT_LEDGER_ENTRY_TYPE_LABELS.get(row.entry_type, "grant"),
        "source_type": CREDIT_SOURCE_TYPE_LABELS.get(row.source_type, "manual"),
        "source_bid": row.source_bid,
        "idempotency_key": row.idempotency_key,
        "amount": _decimal_to_number(row.amount),
        "balance_after": _decimal_to_number(row.balance_after),
        "expires_at": _serialize_dt(app, row.expires_at, timezone_name=timezone_name),
        "consumable_from": _serialize_dt(
            app,
            row.consumable_from,
            timezone_name=timezone_name,
        ),
        "metadata": _normalize_json_value(row.metadata_json) or {},
        "created_at": _serialize_dt(app, row.created_at, timezone_name=timezone_name)
        or "",
    }


def _serialize_order_summary(
    app: Flask,
    row: BillingOrder,
    *,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    subscription_bid = _normalize_bid(row.subscription_bid)
    payment_mode = "subscription"
    if row.order_type not in BILLING_ORDER_TYPE_LABELS:
        payment_mode = "one_time"
    elif not BILLING_ORDER_TYPE_LABELS[row.order_type].startswith("subscription_"):
        payment_mode = "one_time"

    return {
        "billing_order_bid": row.billing_order_bid,
        "creator_bid": row.creator_bid,
        "product_bid": row.product_bid,
        "subscription_bid": subscription_bid or None,
        "order_type": BILLING_ORDER_TYPE_LABELS.get(row.order_type, "manual"),
        "status": BILLING_ORDER_STATUS_LABELS.get(row.status, "init"),
        "payment_provider": str(row.payment_provider or ""),
        "payment_mode": payment_mode,
        "payable_amount": int(row.payable_amount or 0),
        "paid_amount": int(row.paid_amount or 0),
        "currency": row.currency,
        "provider_reference_id": str(row.provider_reference_id or ""),
        "failure_message": str(row.failure_message or ""),
        "created_at": _serialize_dt(app, row.created_at, timezone_name=timezone_name)
        or "",
        "paid_at": _serialize_dt(app, row.paid_at, timezone_name=timezone_name),
    }


def _build_page_payload(
    query, *, page_index: int, page_size: int, serializer
) -> dict[str, Any]:
    total = query.order_by(None).count()
    if total == 0:
        return {
            "items": [],
            "page": page_index,
            "page_count": 0,
            "page_size": page_size,
            "total": 0,
        }

    page_count = (total + page_size - 1) // page_size
    resolved_page = min(page_index, max(page_count, 1))
    offset = (resolved_page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()
    return {
        "items": [serializer(row) for row in rows],
        "page": resolved_page,
        "page_count": page_count,
        "page_size": page_size,
        "total": total,
    }
