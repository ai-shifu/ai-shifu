"""Read-model builders for creator and admin billing surfaces."""

from __future__ import annotations

from typing import Any

from flask import Flask
from sqlalchemy import case

from flaskr.service.common.models import raise_error, raise_param_error

from .consts import (
    BILLING_DOMAIN_BINDING_STATUS_DISABLED,
    BILLING_DOMAIN_BINDING_STATUS_FAILED,
    BILLING_DOMAIN_BINDING_STATUS_PENDING,
    BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
    BILLING_ORDER_STATUS_FAILED,
    BILLING_ORDER_STATUS_PENDING,
    BILLING_ORDER_STATUS_REFUNDED,
    BILLING_ORDER_STATUS_TIMEOUT,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
)
from .domains import build_creator_domain_bindings, manage_creator_domain_binding
from .dtos import (
    AdminBillingDailyLedgerSummaryPageDTO,
    AdminBillingDailyUsageMetricsPageDTO,
    AdminBillingOrdersPageDTO,
    BillingCatalogDTO,
    BillingDailyLedgerSummaryPageDTO,
    BillingDailyUsageMetricsPageDTO,
    BillingDomainAuditsPageDTO,
    BillingDomainBindResultDTO,
    BillingDomainBindingsDTO,
    BillingEntitlementsDTO,
    BillingEntitlementsPageDTO,
    BillingLedgerAdjustResultDTO,
    BillingLedgerPageDTO,
    BillingOrderDetailDTO,
    BillingOrdersPageDTO,
    BillingPlanDTO,
    BillingSubscriptionsPageDTO,
    BillingTopupProductDTO,
    BillingOverviewDTO,
    BillingWalletBucketListDTO,
)
from .entitlements import (
    resolve_creator_entitlement_state,
    serialize_creator_entitlements,
)
from .models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    BillingDomainBinding,
    BillingOrder,
    BillingProduct,
    BillingSubscription,
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .queries import (
    build_list_page_payload as _build_list_page_payload,
    build_page_payload as _build_page_payload,
    load_admin_creator_bids as _load_admin_creator_bids,
    load_latest_renewal_event_map as _load_latest_renewal_event_map,
    load_product_code_map as _load_product_code_map,
    load_wallet_map as _load_wallet_map,
    normalize_pagination,
    normalize_stat_date_filter as _normalize_stat_date_filter,
    resolve_domain_binding_status_filter as _resolve_domain_binding_status_filter,
    resolve_order_status_filter as _resolve_order_status_filter,
    resolve_subscription_status_filter as _resolve_subscription_status_filter,
)
from .serializers import (
    build_billing_alerts as _build_billing_alerts,
    normalize_bid as _normalize_bid,
    normalize_json_object as _normalize_json_object,
    serialize_admin_daily_ledger_summary as _serialize_admin_daily_ledger_summary,
    serialize_admin_daily_usage_metric as _serialize_admin_daily_usage_metric,
    serialize_admin_domain_binding as _serialize_admin_domain_binding,
    serialize_admin_entitlement_state as _serialize_admin_entitlement_state,
    serialize_admin_order_summary as _serialize_admin_order_summary,
    serialize_admin_subscription as _serialize_admin_subscription,
    serialize_daily_ledger_summary as _serialize_daily_ledger_summary,
    serialize_daily_usage_metric as _serialize_daily_usage_metric,
    serialize_dt as _serialize_dt,
    serialize_ledger_entry as _serialize_ledger_entry,
    serialize_order_summary as _serialize_order_summary,
    serialize_product as _serialize_product,
    serialize_subscription as _serialize_subscription,
    to_decimal as _to_decimal,
    serialize_wallet as _serialize_wallet,
    serialize_wallet_bucket as _serialize_wallet_bucket,
    load_current_subscription as _load_current_subscription,
)
from .trials import resolve_new_creator_trial_offer as _resolve_new_creator_trial_offer
from .wallets import adjust_credit_wallet_balance

DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20


def build_billing_catalog(app: Flask) -> BillingCatalogDTO:
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

        plans: list[BillingPlanDTO] = []
        topups: list[BillingTopupProductDTO] = []
        for row in rows:
            payload = _serialize_product(row)
            if isinstance(payload, BillingPlanDTO):
                plans.append(payload)
            elif isinstance(payload, BillingTopupProductDTO):
                topups.append(payload)

        return BillingCatalogDTO(plans=plans, topups=topups)


def build_billing_overview(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> BillingOverviewDTO:
    """Return the wallet snapshot, current subscription, and alerts."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        trial_offer = _resolve_new_creator_trial_offer(
            app,
            normalized_creator_bid,
            trigger="billing_overview",
            timezone_name=timezone_name,
        )
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
        return BillingOverviewDTO(
            creator_bid=normalized_creator_bid,
            wallet=wallet_payload,
            subscription=subscription_payload,
            billing_alerts=_build_billing_alerts(wallet_payload, subscription),
            trial_offer=trial_offer,
        )


def build_billing_entitlements(app: Flask, creator_bid: str) -> BillingEntitlementsDTO:
    """Return the creator entitlement snapshot for v1.1 surfaces."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        state = resolve_creator_entitlement_state(normalized_creator_bid)
        return serialize_creator_entitlements(state)


def build_billing_daily_usage_metrics_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    stat_date_from: str = "",
    stat_date_to: str = "",
    timezone_name: str | None = None,
) -> BillingDailyUsageMetricsPageDTO:
    """Return paginated creator-scoped daily usage aggregate rows."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_stat_date_from = _normalize_stat_date_filter(
        stat_date_from,
        parameter_name="date_from",
    )
    normalized_stat_date_to = _normalize_stat_date_filter(
        stat_date_to,
        parameter_name="date_to",
    )

    with app.app_context():
        query = BillingDailyUsageMetric.query.filter(
            BillingDailyUsageMetric.deleted == 0,
            BillingDailyUsageMetric.creator_bid == normalized_creator_bid,
        )
        if normalized_stat_date_from:
            query = query.filter(
                BillingDailyUsageMetric.stat_date >= normalized_stat_date_from
            )
        if normalized_stat_date_to:
            query = query.filter(
                BillingDailyUsageMetric.stat_date <= normalized_stat_date_to
            )

        query = query.order_by(
            BillingDailyUsageMetric.stat_date.desc(),
            BillingDailyUsageMetric.consumed_credits.desc(),
            BillingDailyUsageMetric.raw_amount.desc(),
            BillingDailyUsageMetric.id.desc(),
        )
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_daily_usage_metric(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )
        return BillingDailyUsageMetricsPageDTO(**payload.to_dto_kwargs())


def build_billing_daily_ledger_summary_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    stat_date_from: str = "",
    stat_date_to: str = "",
    timezone_name: str | None = None,
) -> BillingDailyLedgerSummaryPageDTO:
    """Return paginated creator-scoped daily ledger summary rows."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_stat_date_from = _normalize_stat_date_filter(
        stat_date_from,
        parameter_name="date_from",
    )
    normalized_stat_date_to = _normalize_stat_date_filter(
        stat_date_to,
        parameter_name="date_to",
    )

    with app.app_context():
        query = BillingDailyLedgerSummary.query.filter(
            BillingDailyLedgerSummary.deleted == 0,
            BillingDailyLedgerSummary.creator_bid == normalized_creator_bid,
        )
        if normalized_stat_date_from:
            query = query.filter(
                BillingDailyLedgerSummary.stat_date >= normalized_stat_date_from
            )
        if normalized_stat_date_to:
            query = query.filter(
                BillingDailyLedgerSummary.stat_date <= normalized_stat_date_to
            )

        query = query.order_by(
            BillingDailyLedgerSummary.stat_date.desc(),
            BillingDailyLedgerSummary.entry_count.desc(),
            BillingDailyLedgerSummary.id.desc(),
        )
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_daily_ledger_summary(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )
        return BillingDailyLedgerSummaryPageDTO(**payload.to_dto_kwargs())


def build_billing_wallet_buckets(
    app: Flask,
    creator_bid: str,
    *,
    timezone_name: str | None = None,
) -> BillingWalletBucketListDTO:
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
        return BillingWalletBucketListDTO(
            items=[
                _serialize_wallet_bucket(app, row, timezone_name=timezone_name)
                for row in rows
            ]
        )


def build_billing_ledger_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    timezone_name: str | None = None,
) -> BillingLedgerPageDTO:
    """Return paginated credit ledger entries for a creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    with app.app_context():
        query = CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == normalized_creator_bid,
        ).order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc())
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_ledger_entry(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )
        return BillingLedgerPageDTO(**payload.to_dto_kwargs())


def build_billing_orders_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    timezone_name: str | None = None,
) -> BillingOrdersPageDTO:
    """Return paginated billing orders for a creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    with app.app_context():
        query = BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == normalized_creator_bid,
        ).order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc())
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_order_summary(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )
        return BillingOrdersPageDTO(**payload.to_dto_kwargs())


def build_admin_billing_subscriptions_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    status: str = "",
    timezone_name: str | None = None,
) -> BillingSubscriptionsPageDTO:
    """Return paginated billing subscriptions for the admin billing surface."""

    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    status_code = _resolve_subscription_status_filter(status)

    with app.app_context():
        query = BillingSubscription.query.filter(BillingSubscription.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(
                BillingSubscription.creator_bid == normalized_creator_bid
            )
        if status_code is not None:
            query = query.filter(BillingSubscription.status == status_code)

        query = query.order_by(
            case(
                (
                    BillingSubscription.status == BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
                    1,
                ),
                (
                    BillingSubscription.status == BILLING_SUBSCRIPTION_STATUS_PAUSED,
                    2,
                ),
                (
                    BillingSubscription.status
                    == BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
                    3,
                ),
                else_=9,
            ),
            BillingSubscription.updated_at.desc(),
            BillingSubscription.id.desc(),
        )
        total = query.order_by(None).count()
        if total == 0:
            return BillingSubscriptionsPageDTO(
                items=[],
                page=safe_page_index,
                page_count=0,
                page_size=safe_page_size,
                total=0,
            )

        page_count = (total + safe_page_size - 1) // safe_page_size
        resolved_page = min(safe_page_index, max(page_count, 1))
        offset = (resolved_page - 1) * safe_page_size
        rows = query.offset(offset).limit(safe_page_size).all()

        product_codes = _load_product_code_map(
            [
                *[row.product_bid for row in rows],
                *[
                    row.next_product_bid
                    for row in rows
                    if _normalize_bid(row.next_product_bid)
                ],
            ]
        )
        wallets = _load_wallet_map([row.creator_bid for row in rows])
        renewal_events = _load_latest_renewal_event_map(
            [row.subscription_bid for row in rows]
        )
        return BillingSubscriptionsPageDTO(
            items=[
                _serialize_admin_subscription(
                    app,
                    row,
                    product_codes=product_codes,
                    wallet=wallets.get(row.creator_bid),
                    renewal_event=renewal_events.get(row.subscription_bid),
                    timezone_name=timezone_name,
                )
                for row in rows
            ],
            page=resolved_page,
            page_count=page_count,
            page_size=safe_page_size,
            total=total,
        )


def build_admin_billing_entitlements_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    timezone_name: str | None = None,
) -> BillingEntitlementsPageDTO:
    """Return paginated effective entitlement snapshots for admin billing."""

    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)

    with app.app_context():
        creator_bids = _load_admin_creator_bids(creator_bid=normalized_creator_bid)
        items = [
            _serialize_admin_entitlement_state(
                app,
                resolve_creator_entitlement_state(candidate_creator_bid),
                timezone_name=timezone_name,
            )
            for candidate_creator_bid in creator_bids
        ]
        payload = _build_list_page_payload(
            items,
            page_index=safe_page_index,
            page_size=safe_page_size,
        )
        return BillingEntitlementsPageDTO(**payload.to_dto_kwargs())


def build_admin_billing_domain_audits_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    status: str = "",
    timezone_name: str | None = None,
) -> BillingDomainAuditsPageDTO:
    """Return paginated cross-creator domain binding rows for admin audit."""

    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    status_code = _resolve_domain_binding_status_filter(status)

    with app.app_context():
        query = BillingDomainBinding.query.filter(BillingDomainBinding.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(
                BillingDomainBinding.creator_bid == normalized_creator_bid,
            )
        if status_code is not None:
            query = query.filter(BillingDomainBinding.status == status_code)

        query = query.order_by(
            case(
                (
                    BillingDomainBinding.status
                    == BILLING_DOMAIN_BINDING_STATUS_PENDING,
                    1,
                ),
                (
                    BillingDomainBinding.status == BILLING_DOMAIN_BINDING_STATUS_FAILED,
                    2,
                ),
                (
                    BillingDomainBinding.status
                    == BILLING_DOMAIN_BINDING_STATUS_VERIFIED,
                    3,
                ),
                (
                    BillingDomainBinding.status
                    == BILLING_DOMAIN_BINDING_STATUS_DISABLED,
                    4,
                ),
                else_=9,
            ),
            BillingDomainBinding.updated_at.desc(),
            BillingDomainBinding.id.desc(),
        )

        total = query.order_by(None).count()
        if total == 0:
            return BillingDomainAuditsPageDTO(
                items=[],
                page=safe_page_index,
                page_count=0,
                page_size=safe_page_size,
                total=0,
            )

        page_count = (total + safe_page_size - 1) // safe_page_size
        resolved_page = min(safe_page_index, max(page_count, 1))
        offset = (resolved_page - 1) * safe_page_size
        rows = query.offset(offset).limit(safe_page_size).all()
        entitlement_flags = {
            candidate_creator_bid: bool(
                resolve_creator_entitlement_state(
                    candidate_creator_bid
                ).custom_domain_enabled
            )
            for candidate_creator_bid in {
                _normalize_bid(row.creator_bid) for row in rows if row.creator_bid
            }
        }
        return BillingDomainAuditsPageDTO(
            items=[
                _serialize_admin_domain_binding(
                    app,
                    row,
                    custom_domain_enabled=entitlement_flags.get(
                        _normalize_bid(row.creator_bid),
                        False,
                    ),
                    timezone_name=timezone_name,
                )
                for row in rows
            ],
            page=resolved_page,
            page_count=page_count,
            page_size=safe_page_size,
            total=total,
        )


def build_admin_billing_orders_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    status: str = "",
    timezone_name: str | None = None,
) -> AdminBillingOrdersPageDTO:
    """Return paginated billing orders for the admin billing surface."""

    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    status_code = _resolve_order_status_filter(status)

    with app.app_context():
        query = BillingOrder.query.filter(BillingOrder.deleted == 0)
        if normalized_creator_bid:
            query = query.filter(BillingOrder.creator_bid == normalized_creator_bid)
        if status_code is not None:
            query = query.filter(BillingOrder.status == status_code)

        query = query.order_by(
            case(
                (BillingOrder.status == BILLING_ORDER_STATUS_FAILED, 1),
                (BillingOrder.status == BILLING_ORDER_STATUS_PENDING, 2),
                (BillingOrder.status == BILLING_ORDER_STATUS_TIMEOUT, 3),
                (BillingOrder.status == BILLING_ORDER_STATUS_REFUNDED, 4),
                else_=9,
            ),
            BillingOrder.created_at.desc(),
            BillingOrder.id.desc(),
        )
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_admin_order_summary(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )
        return AdminBillingOrdersPageDTO(**payload.to_dto_kwargs())


def build_admin_billing_daily_usage_metrics_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    stat_date_from: str = "",
    stat_date_to: str = "",
    timezone_name: str | None = None,
) -> AdminBillingDailyUsageMetricsPageDTO:
    """Return paginated cross-creator daily usage rows for admin reporting."""

    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_stat_date_from = _normalize_stat_date_filter(
        stat_date_from,
        parameter_name="date_from",
    )
    normalized_stat_date_to = _normalize_stat_date_filter(
        stat_date_to,
        parameter_name="date_to",
    )

    with app.app_context():
        query = BillingDailyUsageMetric.query.filter(
            BillingDailyUsageMetric.deleted == 0
        )
        if normalized_creator_bid:
            query = query.filter(
                BillingDailyUsageMetric.creator_bid == normalized_creator_bid,
            )
        if normalized_stat_date_from:
            query = query.filter(
                BillingDailyUsageMetric.stat_date >= normalized_stat_date_from
            )
        if normalized_stat_date_to:
            query = query.filter(
                BillingDailyUsageMetric.stat_date <= normalized_stat_date_to
            )

        query = query.order_by(
            BillingDailyUsageMetric.stat_date.desc(),
            BillingDailyUsageMetric.creator_bid.asc(),
            BillingDailyUsageMetric.consumed_credits.desc(),
            BillingDailyUsageMetric.raw_amount.desc(),
            BillingDailyUsageMetric.id.desc(),
        )
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_admin_daily_usage_metric(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )
        return AdminBillingDailyUsageMetricsPageDTO(**payload.to_dto_kwargs())


def build_admin_billing_daily_ledger_summary_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_bid: str = "",
    stat_date_from: str = "",
    stat_date_to: str = "",
    timezone_name: str | None = None,
) -> AdminBillingDailyLedgerSummaryPageDTO:
    """Return paginated cross-creator daily ledger rows for admin reporting."""

    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_stat_date_from = _normalize_stat_date_filter(
        stat_date_from,
        parameter_name="date_from",
    )
    normalized_stat_date_to = _normalize_stat_date_filter(
        stat_date_to,
        parameter_name="date_to",
    )

    with app.app_context():
        query = BillingDailyLedgerSummary.query.filter(
            BillingDailyLedgerSummary.deleted == 0,
        )
        if normalized_creator_bid:
            query = query.filter(
                BillingDailyLedgerSummary.creator_bid == normalized_creator_bid,
            )
        if normalized_stat_date_from:
            query = query.filter(
                BillingDailyLedgerSummary.stat_date >= normalized_stat_date_from
            )
        if normalized_stat_date_to:
            query = query.filter(
                BillingDailyLedgerSummary.stat_date <= normalized_stat_date_to
            )

        query = query.order_by(
            BillingDailyLedgerSummary.stat_date.desc(),
            BillingDailyLedgerSummary.creator_bid.asc(),
            BillingDailyLedgerSummary.entry_count.desc(),
            BillingDailyLedgerSummary.id.desc(),
        )
        payload = _build_page_payload(
            query,
            page_index=safe_page_index,
            page_size=safe_page_size,
            serializer=lambda row: _serialize_admin_daily_ledger_summary(
                app,
                row,
                timezone_name=timezone_name,
            ),
        )
        return AdminBillingDailyLedgerSummaryPageDTO(**payload.to_dto_kwargs())


def build_billing_order_detail(
    app: Flask,
    creator_bid: str,
    billing_order_bid: str,
    *,
    timezone_name: str | None = None,
) -> BillingOrderDetailDTO:
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
        return BillingOrderDetailDTO(
            **payload.__json__(),
            metadata=_normalize_json_object(row.metadata_json).to_metadata_json(),
            failure_code=str(row.failure_code or ""),
            refunded_at=_serialize_dt(
                app,
                row.refunded_at,
                timezone_name=timezone_name,
            ),
            failed_at=_serialize_dt(
                app,
                row.failed_at,
                timezone_name=timezone_name,
            ),
        )


def build_admin_billing_domain_bindings(
    app: Flask,
    *,
    creator_bid: str,
    timezone_name: str | None = None,
) -> BillingDomainBindingsDTO:
    """Return creator-scoped custom domain bindings for admin billing pages."""

    return build_creator_domain_bindings(
        app,
        creator_bid,
        timezone_name=timezone_name,
    )


def bind_admin_billing_domain(
    app: Flask,
    *,
    creator_bid: str,
    payload: dict[str, Any],
    timezone_name: str | None = None,
) -> BillingDomainBindResultDTO:
    """Create, verify, or disable a creator custom domain binding."""

    return manage_creator_domain_binding(
        app,
        creator_bid,
        payload,
        timezone_name=timezone_name,
    )


def adjust_admin_billing_ledger(
    app: Flask,
    *,
    operator_user_bid: str,
    payload: dict[str, Any],
) -> BillingLedgerAdjustResultDTO:
    """Apply a manual admin ledger adjustment through wallet buckets."""

    normalized_creator_bid = _normalize_bid(payload.get("creator_bid"))
    if not normalized_creator_bid:
        raise_param_error("creator_bid")

    amount = payload.get("amount")
    try:
        normalized_amount = _to_decimal(amount)
    except Exception:
        raise_param_error("amount")
    if normalized_amount == 0:
        raise_param_error("amount")

    note = str(payload.get("note") or payload.get("reason") or "").strip()
    if len(note) > 255:
        raise_param_error("note")

    return adjust_credit_wallet_balance(
        app,
        creator_bid=normalized_creator_bid,
        amount=normalized_amount,
        note=note,
        operator_user_bid=_normalize_bid(operator_user_bid),
    )
