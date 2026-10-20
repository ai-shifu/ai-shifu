"""Read-model builders for creator and admin billing surfaces."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from flaskr.dao import db  # noqa: F401 - re-exported for import compatibility
from flaskr.i18n import (
    _ as translate,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.i18n import (  # noqa: F401 - re-exported for import compatibility
    get_current_language,
    set_language,
)
from flaskr.service.common.models import (  # noqa: F401 - re-exported for import compatibility
    raise_error,
    raise_param_error,
)
from flaskr.service.common.pagination import (
    DEFAULT_PAGE_INDEX,
    DEFAULT_PAGE_SIZE,
    normalize_pagination,
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,  # noqa: F401 - re-exported for import compatibility
    BILL_USAGE_SCENE_PREVIEW,  # noqa: F401 - re-exported for import compatibility
    BILL_USAGE_SCENE_PROD,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.metering.models import (
    BillUsageRecord,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.shifu.models import (  # noqa: F401 - re-exported for import compatibility
    DraftShifu,
    PublishedShifu,
)
from flaskr.service.user.models import (
    AuthCredential,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.service.user.models import (
    UserInfo as UserEntity,  # noqa: F401 - re-exported for import compatibility
)
from flaskr.util.datetime import (
    NAIVE_DATETIME_MAX,
    NAIVE_DATETIME_MIN,
    now_utc,
    parse_naive_utc,  # noqa: F401 - re-exported for import compatibility
)

from .bucket_categories import (
    OrderTypeLoader,
    resolve_credit_bucket_priority,
)
from .campaigns import resolve_catalog_campaign_payload
from .consts import (
    BILLING_ORDER_STATUS_CANCELED,  # noqa: F401 - re-exported for import compatibility
    BILLING_ORDER_STATUS_PAID,  # noqa: F401 - re-exported for import compatibility
    BILLING_ORDER_STATUS_PENDING,  # noqa: F401 - re-exported for import compatibility
    BILLING_ORDER_STATUS_REFUNDED,  # noqa: F401 - re-exported for import compatibility
    BILLING_ORDER_STATUS_TIMEOUT,  # noqa: F401 - re-exported for import compatibility
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,  # noqa: F401 - re-exported for import compatibility
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,  # noqa: F401 - re-exported for import compatibility
    BILLING_SUBSCRIPTION_STATUS_PAUSED,  # noqa: F401 - re-exported for import compatibility
    BILLING_TRIAL_PRODUCT_CODE,  # noqa: F401 - re-exported for import compatibility
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,  # noqa: F401 - re-exported for import compatibility
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,  # noqa: F401 - re-exported for import compatibility
    CREDIT_SOURCE_TYPE_LABELS,  # noqa: F401 - re-exported for import compatibility
    CREDIT_SOURCE_TYPE_MANUAL,  # noqa: F401 - re-exported for import compatibility
    CREDIT_SOURCE_TYPE_USAGE,
)
from .credit_grant_allocation_views import (
    CreditAllocationView,
    build_credit_allocation_view,
    build_credit_grant_view,
)
from .credit_notifications import build_creator_limit_state_for_available_credits
from .dtos import (
    AdminBillingDailyLedgerSummaryPageDTO,  # noqa: F401 - re-exported for import compatibility
    AdminBillingDailyUsageMetricsPageDTO,  # noqa: F401 - re-exported for import compatibility
    AdminBillingFocusTeacherDTO,  # noqa: F401 - re-exported for import compatibility
    AdminBillingFocusTeachersPageDTO,  # noqa: F401 - re-exported for import compatibility
    BillingCatalogDTO,
    BillingEntitlementsPageDTO,  # noqa: F401 - re-exported for import compatibility
    BillingLedgerAdjustResultDTO,  # noqa: F401 - re-exported for import compatibility
    BillingLedgerPageDTO,
    BillingOverviewDTO,
    BillingPlanDTO,
    BillingSubscriptionsPageDTO,  # noqa: F401 - re-exported for import compatibility
    BillingTopupProductDTO,
    BillingWalletBucketListDTO,
    OperatorCreditOrderDetailDTO,  # noqa: F401 - re-exported for import compatibility
    OperatorCreditOrderGrantDTO,  # noqa: F401 - re-exported for import compatibility
    OperatorCreditOrderOverviewDTO,  # noqa: F401 - re-exported for import compatibility
    OperatorCreditOrdersPageDTO,  # noqa: F401 - re-exported for import compatibility
)
from .entitlements import (
    resolve_creator_entitlement_state,  # noqa: F401 - re-exported for import compatibility
)
from .models import (
    BillingDailyLedgerSummary,  # noqa: F401 - re-exported for import compatibility
    BillingDailyUsageMetric,  # noqa: F401 - re-exported for import compatibility
    BillingEntitlement,  # noqa: F401 - re-exported for import compatibility
    BillingOrder,
    BillingProduct,
    BillingSubscription,  # noqa: F401 - re-exported for import compatibility
    CreditLedgerEntry,
    CreditWallet,
    CreditWalletBucket,
)
from .primitives import credit_decimal_to_number, is_billing_enabled
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .queries import (
    load_current_subscription as _load_current_subscription,
)
from .read_model_lookups import (
    _build_usage_metadata_map,
    _filter_out_reserved_credit_grant_ledgers,
    _is_public_trial_catalog_product,
)
from .serializers import (
    build_billing_alerts as _build_billing_alerts,
)
from .serializers import (
    serialize_ledger_entry as _serialize_ledger_entry,
)
from .serializers import (
    serialize_product as _serialize_product,
)
from .serializers import (
    serialize_subscription as _serialize_subscription,
)
from .serializers import (
    serialize_wallet as _serialize_wallet,
)
from .serializers import (
    serialize_wallet_bucket as _serialize_wallet_bucket,
)
from .trials import resolve_new_creator_trial_offer as _resolve_new_creator_trial_offer
from .wallets import (
    adjust_credit_wallet_balance,  # noqa: F401 - re-exported for import compatibility
    calculate_credit_wallet_snapshot_values,
)

# Re-exported public API: admin and operator read models live in sibling
# modules; these imports keep every historical ``read_models`` path working.
# isort: split
from .admin_read_models import (
    adjust_admin_billing_ledger,  # noqa: F401 - re-exported for import compatibility
    build_admin_bill_daily_ledger_summary_page,  # noqa: F401 - re-exported for import compatibility
    build_admin_bill_daily_usage_metrics_page,  # noqa: F401 - re-exported for import compatibility
    build_admin_bill_entitlements_page,  # noqa: F401 - re-exported for import compatibility
    build_admin_bill_subscriptions_page,  # noqa: F401 - re-exported for import compatibility
    build_admin_billing_focus_teachers_page,  # noqa: F401 - re-exported for import compatibility
)
from .operator_credit_order_read_models import (
    build_operator_credit_orders_overview,  # noqa: F401 - re-exported for import compatibility
    build_operator_credit_orders_page,  # noqa: F401 - re-exported for import compatibility
    get_operator_credit_order_detail,  # noqa: F401 - re-exported for import compatibility
)

if TYPE_CHECKING:
    from datetime import datetime

    from flask import Flask


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
            if _is_public_trial_catalog_product(row):
                continue
            payload = _serialize_product(
                row,
                campaign_payload=resolve_catalog_campaign_payload(row),
            )
            if isinstance(payload, BillingPlanDTO):
                plans.append(payload)
            elif isinstance(payload, BillingTopupProductDTO):
                topups.append(payload)

        return BillingCatalogDTO(plans=plans, topups=topups)


def build_billing_overview(
    app: Flask,
    creator_bid: str,
) -> BillingOverviewDTO:
    """Return the wallet snapshot, current subscription, and alerts."""
    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        trial_offer = _resolve_new_creator_trial_offer(
            normalized_creator_bid,
            trigger="billing_overview",
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
        available_credits = Decimal(0)
        if wallet is not None:
            available_credits, reserved_credits = (
                calculate_credit_wallet_snapshot_values(
                    wallet,
                    snapshot_at=now_utc(),
                )
            )
            wallet_payload.available_credits = credit_decimal_to_number(
                available_credits
            )
            wallet_payload.reserved_credits = credit_decimal_to_number(reserved_credits)
        subscription_payload = _serialize_subscription(app, subscription)
        limit_state = (
            build_creator_limit_state_for_available_credits(available_credits)
            if is_billing_enabled()
            else {
                "state": "normal",
                "debug_allowed": True,
                "available_credits": "0",
                "softlimit_threshold": "0",
            }
        )
        softlimit_threshold = limit_state.get("softlimit_threshold")
        return BillingOverviewDTO(
            creator_bid=normalized_creator_bid,
            wallet=wallet_payload,
            subscription=subscription_payload,
            billing_alerts=_build_billing_alerts(wallet_payload, subscription),
            trial_offer=trial_offer,
            credit_status=str(limit_state.get("state") or "normal"),
            debug_allowed=bool(limit_state.get("debug_allowed", True)),
            softlimit_threshold=(
                str(softlimit_threshold) if softlimit_threshold is not None else None
            ),
        )


def build_billing_wallet_buckets(
    app: Flask,
    creator_bid: str,
) -> BillingWalletBucketListDTO:
    """Return wallet bucket projections sorted by actual consumption order."""
    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        rows = (
            CreditWalletBucket.query.filter(
                CreditWalletBucket.deleted == 0,
                CreditWalletBucket.creator_bid == normalized_creator_bid,
            )
            .order_by(CreditWalletBucket.id.asc())
            .all()
        )
        load_order_type = _build_wallet_bucket_order_type_loader(
            rows,
            creator_bid=normalized_creator_bid,
        )
        bucket_views = [
            (
                row,
                build_credit_allocation_view(
                    row,
                    load_order_type=load_order_type,
                ),
            )
            for row in rows
        ]
        bucket_views.sort(
            key=lambda pair: _wallet_bucket_view_sort_key(pair[0], pair[1])
        )
        items = []
        for row, allocation_view in bucket_views:
            items.append(
                _serialize_wallet_bucket(
                    app,
                    row,
                    category_code=allocation_view.runtime_bucket_category,
                    credit_asset_kind=allocation_view.asset_kind,
                )
            )
        return BillingWalletBucketListDTO(items=items)


def _wallet_bucket_view_sort_key(
    row: CreditWalletBucket,
    allocation_view: CreditAllocationView,
) -> tuple[int, bool, datetime, datetime, int]:
    return (
        resolve_credit_bucket_priority(allocation_view.runtime_bucket_category),
        row.effective_to is None,
        row.effective_to or NAIVE_DATETIME_MAX,
        row.created_at or NAIVE_DATETIME_MIN,
        int(row.id or 0),
    )


def _build_wallet_bucket_order_type_loader(
    rows: list[CreditWalletBucket],
    *,
    creator_bid: str,
) -> OrderTypeLoader:
    order_bids = {
        _normalize_bid(_normalize_json_object(row.metadata_json).get("bill_order_bid"))
        for row in rows
    }
    order_bids.discard("")

    return _build_creator_order_type_loader(order_bids, creator_bid=creator_bid)


def _build_creator_order_type_loader(
    order_bids: set[str],
    *,
    creator_bid: str,
) -> OrderTypeLoader:
    safe_order_bids = {_normalize_bid(order_bid) for order_bid in order_bids}
    safe_order_bids.discard("")

    orders = (
        BillingOrder.query.filter(
            BillingOrder.deleted == 0,
            BillingOrder.creator_bid == _normalize_bid(creator_bid),
            BillingOrder.bill_order_bid.in_(safe_order_bids),
        ).all()
        if safe_order_bids
        else []
    )
    order_type_by_bid = {
        _normalize_bid(order.bill_order_bid): int(order.order_type or 0)
        for order in orders
    }

    def _load_order_type(order_bid: str) -> int | None:
        return order_type_by_bid.get(_normalize_bid(order_bid))

    return _load_order_type


def _load_ledger_bucket_map(
    rows: list[CreditLedgerEntry],
    *,
    creator_bid: str,
) -> dict[str, CreditWalletBucket]:
    bucket_bids = {
        _normalize_bid(row.wallet_bucket_bid)
        for row in rows
        if _normalize_bid(row.wallet_bucket_bid)
    }
    if not bucket_bids:
        return {}

    buckets = CreditWalletBucket.query.filter(
        CreditWalletBucket.deleted == 0,
        CreditWalletBucket.creator_bid == _normalize_bid(creator_bid),
        CreditWalletBucket.wallet_bucket_bid.in_(bucket_bids),
    ).all()
    return {_normalize_bid(bucket.wallet_bucket_bid): bucket for bucket in buckets}


def _build_ledger_page_order_type_loader(
    rows: list[CreditLedgerEntry],
    *,
    creator_bid: str,
    bucket_map: dict[str, CreditWalletBucket],
) -> OrderTypeLoader:
    order_bids = {
        _normalize_bid(_normalize_json_object(row.metadata_json).get("bill_order_bid"))
        for row in rows
    }
    order_bids.update(
        _normalize_bid(
            _normalize_json_object(bucket.metadata_json).get("bill_order_bid")
        )
        for bucket in bucket_map.values()
    )
    order_bids.discard("")

    return _build_creator_order_type_loader(order_bids, creator_bid=creator_bid)


def build_billing_ledger_page(
    app: Flask,
    creator_bid: str,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> BillingLedgerPageDTO:
    """Return paginated credit ledger entries for a creator."""
    normalized_creator_bid = _normalize_bid(creator_bid)
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    with app.app_context():
        query = CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.creator_bid == normalized_creator_bid,
        )
        query = _filter_out_reserved_credit_grant_ledgers(query).order_by(
            CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc()
        )
        total = query.order_by(None).count()
        if total == 0:
            return BillingLedgerPageDTO(
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
        usage_metadata_map = _build_usage_metadata_map(rows)
        bucket_map = _load_ledger_bucket_map(rows, creator_bid=normalized_creator_bid)
        load_order_type = _build_ledger_page_order_type_loader(
            rows,
            creator_bid=normalized_creator_bid,
            bucket_map=bucket_map,
        )

        items = []
        for row in rows:
            metadata = _normalize_json_object(row.metadata_json).to_metadata_json()
            if int(row.source_type or 0) == CREDIT_SOURCE_TYPE_USAGE:
                usage_bid = _normalize_bid(metadata.get("usage_bid")) or _normalize_bid(
                    row.source_bid
                )
                usage_metadata = usage_metadata_map.get(usage_bid, {})
                if usage_metadata:
                    metadata = {
                        **metadata,
                        **{
                            key: value
                            for key, value in usage_metadata.items()
                            if value not in (None, "")
                        },
                    }

            credit_view = build_credit_grant_view(
                row,
                bucket=bucket_map.get(_normalize_bid(row.wallet_bucket_bid)),
                load_order_type=load_order_type,
            )
            items.append(
                _serialize_ledger_entry(
                    app,
                    row,
                    metadata=metadata,
                    credit_asset_kind=credit_view.asset_kind,
                )
            )

        return BillingLedgerPageDTO(
            items=items,
            page=resolved_page,
            page_count=page_count,
            page_size=safe_page_size,
            total=total,
        )
