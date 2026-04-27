"""Read-model builders for creator and admin billing surfaces."""

from __future__ import annotations

from typing import Any

from flask import Flask
from sqlalchemy import case

from flaskr.i18n import _ as translate
from flaskr.i18n import get_current_language, set_language
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.service.metering.consts import BILL_USAGE_SCENE_PROD
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential, UserInfo as UserEntity

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
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_SUBSCRIPTION_STATUS_CANCEL_SCHEDULED,
    BILLING_SUBSCRIPTION_STATUS_PAST_DUE,
    BILLING_SUBSCRIPTION_STATUS_PAUSED,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_USAGE,
)
from .bucket_categories import (
    build_wallet_bucket_runtime_sort_key,
    load_billing_order_type_by_bid,
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
    OperatorCreditOrderDetailDTO,
    OperatorCreditOrdersPageDTO,
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
    load_current_subscription as _load_current_subscription,
    load_latest_renewal_event_map as _load_latest_renewal_event_map,
    load_product_code_map as _load_product_code_map,
    load_wallet_map as _load_wallet_map,
    normalize_pagination,
    normalize_stat_date_filter as _normalize_stat_date_filter,
    resolve_domain_binding_status_filter as _resolve_domain_binding_status_filter,
    resolve_order_status_filter as _resolve_order_status_filter,
    resolve_subscription_status_filter as _resolve_subscription_status_filter,
)
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .primitives import serialize_dt as _serialize_dt
from .primitives import to_decimal as _to_decimal
from .serializers import (
    build_billing_alerts as _build_billing_alerts,
    serialize_admin_daily_ledger_summary as _serialize_admin_daily_ledger_summary,
    serialize_admin_daily_usage_metric as _serialize_admin_daily_usage_metric,
    serialize_admin_domain_binding as _serialize_admin_domain_binding,
    serialize_admin_entitlement_state as _serialize_admin_entitlement_state,
    serialize_admin_order_summary as _serialize_admin_order_summary,
    serialize_admin_subscription as _serialize_admin_subscription,
    serialize_daily_ledger_summary as _serialize_daily_ledger_summary,
    serialize_daily_usage_metric as _serialize_daily_usage_metric,
    serialize_ledger_entry as _serialize_ledger_entry,
    serialize_operator_credit_order as _serialize_operator_credit_order,
    serialize_operator_credit_order_grant as _serialize_operator_credit_order_grant,
    serialize_order_summary as _serialize_order_summary,
    serialize_product as _serialize_product,
    serialize_subscription as _serialize_subscription,
    serialize_wallet as _serialize_wallet,
    serialize_wallet_bucket as _serialize_wallet_bucket,
)
from .trials import resolve_new_creator_trial_offer as _resolve_new_creator_trial_offer
from .wallets import adjust_credit_wallet_balance

DEFAULT_PAGE_INDEX = 1
DEFAULT_PAGE_SIZE = 20
_OPERATOR_PRODUCT_FILTER_LANGUAGES = ("zh-CN", "en-US")


def _is_public_trial_catalog_product(row: BillingProduct) -> bool:
    if str(row.product_code or "").strip() == BILLING_TRIAL_PRODUCT_CODE:
        return True
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return bool(metadata.get(BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG))


def _resolve_credit_order_product_search_terms(product: BillingProduct) -> list[str]:
    terms = []
    for candidate in (
        product.product_bid,
        product.product_code,
        product.display_name_i18n_key,
    ):
        normalized_candidate = str(candidate or "").strip()
        if normalized_candidate:
            terms.append(normalized_candidate)

    display_name_key = str(product.display_name_i18n_key or "").strip()
    if not display_name_key:
        return terms

    original_language = get_current_language()
    try:
        for language in _OPERATOR_PRODUCT_FILTER_LANGUAGES:
            set_language(language)
            translated_name = str(translate(display_name_key) or "").strip()
            if translated_name and translated_name != display_name_key:
                terms.append(translated_name)
    finally:
        set_language(original_language)

    return terms


def _load_matching_credit_order_product_bids(keyword: str) -> list[str]:
    normalized_keyword = str(keyword or "").strip().lower()
    if not normalized_keyword:
        return []

    products = BillingProduct.query.order_by(BillingProduct.id.desc()).all()
    matched_product_bids: list[str] = []
    for product in products:
        search_terms = _resolve_credit_order_product_search_terms(product)
        if any(normalized_keyword in term.lower() for term in search_terms):
            normalized_product_bid = str(product.product_bid or "").strip()
            if normalized_product_bid:
                matched_product_bids.append(normalized_product_bid)
    return matched_product_bids


def _load_usage_record_map(usage_bids: list[str]) -> dict[str, BillUsageRecord]:
    normalized_usage_bids = [_normalize_bid(bid) for bid in usage_bids if bid]
    if not normalized_usage_bids:
        return {}

    rows = (
        BillUsageRecord.query.filter(
            BillUsageRecord.usage_bid.in_(normalized_usage_bids)
        )
        .order_by(BillUsageRecord.usage_bid.asc(), BillUsageRecord.id.desc())
        .all()
    )
    payload: dict[str, BillUsageRecord] = {}
    for row in rows:
        payload.setdefault(str(row.usage_bid or "").strip(), row)
    return payload


def _load_shifu_title_maps(
    shifu_bids: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    normalized_shifu_bids = [_normalize_bid(bid) for bid in shifu_bids if bid]
    if not normalized_shifu_bids:
        return {}, {}

    published_titles: dict[str, str] = {}
    published_rows = (
        PublishedShifu.query.filter(
            PublishedShifu.deleted == 0,
            PublishedShifu.shifu_bid.in_(normalized_shifu_bids),
        )
        .order_by(PublishedShifu.shifu_bid.asc(), PublishedShifu.id.desc())
        .all()
    )
    for row in published_rows:
        published_titles.setdefault(
            str(row.shifu_bid or "").strip(), str(row.title or "")
        )

    draft_titles: dict[str, str] = {}
    draft_rows = (
        DraftShifu.query.filter(
            DraftShifu.deleted == 0,
            DraftShifu.shifu_bid.in_(normalized_shifu_bids),
        )
        .order_by(DraftShifu.shifu_bid.asc(), DraftShifu.id.desc())
        .all()
    )
    for row in draft_rows:
        draft_titles.setdefault(str(row.shifu_bid or "").strip(), str(row.title or ""))

    return published_titles, draft_titles


def _load_user_identify_map(user_bids: list[str]) -> dict[str, str]:
    normalized_user_bids = [_normalize_bid(bid) for bid in user_bids if bid]
    if not normalized_user_bids:
        return {}

    rows = UserEntity.query.filter(
        UserEntity.deleted == 0,
        UserEntity.user_bid.in_(normalized_user_bids),
    ).all()
    return {
        str(row.user_bid or "").strip(): str(row.user_identify or "") for row in rows
    }


def _load_operator_creator_map(user_bids: list[str]) -> dict[str, dict[str, str]]:
    normalized_user_bids = [_normalize_bid(bid) for bid in user_bids if bid]
    if not normalized_user_bids:
        return {}

    users = (
        UserEntity.query.filter(
            UserEntity.deleted == 0,
            UserEntity.user_bid.in_(normalized_user_bids),
        )
        .order_by(UserEntity.id.desc())
        .all()
    )
    credentials = (
        AuthCredential.query.filter(
            AuthCredential.deleted == 0,
            AuthCredential.user_bid.in_(normalized_user_bids),
            AuthCredential.provider_name.in_(["phone", "email"]),
        )
        .order_by(AuthCredential.id.desc())
        .all()
    )

    credential_map: dict[str, dict[str, str]] = {}
    for credential in credentials:
        user_bid = str(credential.user_bid or "").strip()
        if not user_bid:
            continue
        payload = credential_map.setdefault(user_bid, {})
        identifier = str(credential.identifier or "").strip()
        if (
            credential.provider_name == "phone"
            and identifier
            and not payload.get("mobile")
        ):
            payload["mobile"] = identifier
        if (
            credential.provider_name == "email"
            and identifier
            and not payload.get("email")
        ):
            payload["email"] = identifier

    payload: dict[str, dict[str, str]] = {}
    for user in users:
        user_bid = str(user.user_bid or "").strip()
        identify = str(user.user_identify or "").strip()
        mobile = str(credential_map.get(user_bid, {}).get("mobile") or "").strip()
        email = str(credential_map.get(user_bid, {}).get("email") or "").strip()
        if not mobile and identify.isdigit():
            mobile = identify
        if not email and "@" in identify:
            email = identify
        payload[user_bid] = {
            "identify": identify,
            "mobile": mobile,
            "email": email,
            "nickname": str(user.nickname or "").strip(),
        }
    return payload


def _load_credit_order_product_map(
    product_bids: list[str],
) -> dict[str, BillingProduct]:
    normalized_product_bids = [_normalize_bid(bid) for bid in product_bids if bid]
    if not normalized_product_bids:
        return {}

    rows = (
        BillingProduct.query.filter(
            BillingProduct.product_bid.in_(normalized_product_bids),
        )
        .order_by(BillingProduct.id.desc())
        .all()
    )
    payload: dict[str, BillingProduct] = {}
    for row in rows:
        payload.setdefault(str(row.product_bid or "").strip(), row)
    return payload


def _load_credit_order_grant_map(
    app: Flask,
    order_bids: list[str],
    *,
    timezone_name: str | None = None,
):
    normalized_order_bids = [_normalize_bid(bid) for bid in order_bids if bid]
    if not normalized_order_bids:
        return {}

    rows = (
        CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.source_bid.in_(normalized_order_bids),
            CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_GRANT,
        )
        .order_by(
            CreditLedgerEntry.source_bid.asc(),
            CreditLedgerEntry.id.desc(),
        )
        .all()
    )
    payload = {}
    for row in rows:
        source_bid = str(row.source_bid or "").strip()
        if not source_bid or source_bid in payload:
            continue
        source_type_label = CREDIT_SOURCE_TYPE_LABELS.get(int(row.source_type or 0), "")
        payload[source_bid] = _serialize_operator_credit_order_grant(
            app,
            source_type=source_type_label,
            source_bid=source_bid,
            granted_credits=row.amount,
            valid_from=row.consumable_from,
            valid_to=row.expires_at,
            timezone_name=timezone_name,
        )
    return payload


def _load_matching_creator_bids_for_keyword(keyword: str) -> list[str]:
    normalized = str(keyword or "").strip()
    if not normalized:
        return []

    matched_bids: set[str] = set()

    users = UserEntity.query.filter(
        UserEntity.deleted == 0,
        (
            (UserEntity.user_bid == normalized)
            | (UserEntity.user_identify == normalized)
            | (UserEntity.user_identify.ilike(f"%{normalized}%"))
        ),
    ).all()
    for user in users:
        user_bid = str(user.user_bid or "").strip()
        if user_bid:
            matched_bids.add(user_bid)

    credentials = AuthCredential.query.filter(
        AuthCredential.deleted == 0,
        AuthCredential.provider_name.in_(["phone", "email"]),
        AuthCredential.identifier.ilike(f"%{normalized}%"),
    ).all()
    for credential in credentials:
        user_bid = str(credential.user_bid or "").strip()
        if user_bid:
            matched_bids.add(user_bid)

    return [user_bid for user_bid in matched_bids if user_bid]


def _resolve_usage_course_name(
    usage: BillUsageRecord,
    *,
    published_titles: dict[str, str],
    draft_titles: dict[str, str],
) -> str:
    shifu_bid = str(usage.shifu_bid or "").strip()
    if not shifu_bid:
        return ""

    published_title = str(published_titles.get(shifu_bid) or "").strip()
    draft_title = str(draft_titles.get(shifu_bid) or "").strip()
    if int(usage.usage_scene or 0) == BILL_USAGE_SCENE_PROD:
        return published_title or draft_title
    return draft_title or published_title


def _build_usage_metadata_map(
    rows: list[CreditLedgerEntry],
) -> dict[str, dict[str, Any]]:
    usage_bids: list[str] = []
    for row in rows:
        if int(row.source_type or 0) != CREDIT_SOURCE_TYPE_USAGE:
            continue
        metadata = _normalize_json_object(row.metadata_json)
        usage_bid = _normalize_bid(metadata.get("usage_bid")) or _normalize_bid(
            row.source_bid
        )
        if usage_bid:
            usage_bids.append(usage_bid)

    usage_map = _load_usage_record_map(usage_bids)
    published_titles, draft_titles = _load_shifu_title_maps(
        [str(item.shifu_bid or "").strip() for item in usage_map.values()]
    )
    user_identify_map = _load_user_identify_map(
        [str(item.user_bid or "").strip() for item in usage_map.values()]
    )

    payload: dict[str, dict[str, Any]] = {}
    for usage_bid, usage in usage_map.items():
        course_name = _resolve_usage_course_name(
            usage,
            published_titles=published_titles,
            draft_titles=draft_titles,
        )
        user_identify = user_identify_map.get(str(usage.user_bid or "").strip(), "")

        metadata: dict[str, Any] = {}
        if course_name:
            metadata["course_name"] = course_name
        if user_identify:
            metadata["user_identify"] = user_identify
        if metadata:
            payload[usage_bid] = metadata

    return payload


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


def build_bill_entitlements(app: Flask, creator_bid: str) -> BillingEntitlementsDTO:
    """Return the creator entitlement snapshot for v1.1 surfaces."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    with app.app_context():
        state = resolve_creator_entitlement_state(normalized_creator_bid)
        return serialize_creator_entitlements(state)


def build_bill_daily_usage_metrics_page(
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


def build_bill_daily_ledger_summary_page(
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
            .order_by(CreditWalletBucket.id.asc())
            .all()
        )
        rows.sort(
            key=lambda row: build_wallet_bucket_runtime_sort_key(
                row,
                load_order_type=load_billing_order_type_by_bid,
            )
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

            items.append(
                _serialize_ledger_entry(
                    app,
                    row,
                    metadata=metadata,
                    timezone_name=timezone_name,
                )
            )

        return BillingLedgerPageDTO(
            items=items,
            page=resolved_page,
            page_count=page_count,
            page_size=safe_page_size,
            total=total,
        )


def build_bill_orders_page(
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


def build_admin_bill_subscriptions_page(
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


def build_admin_bill_entitlements_page(
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


def build_admin_bill_orders_page(
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


def _resolve_credit_order_kind_filter(kind: str) -> int | None:
    normalized_kind = str(kind or "").strip().lower()
    if not normalized_kind:
        return None
    if normalized_kind == "plan":
        return BILLING_PRODUCT_TYPE_PLAN
    if normalized_kind == "topup":
        return BILLING_PRODUCT_TYPE_TOPUP
    raise_param_error("credit_order_kind")


def build_operator_credit_orders_page(
    app: Flask,
    *,
    page_index: int = DEFAULT_PAGE_INDEX,
    page_size: int = DEFAULT_PAGE_SIZE,
    creator_keyword: str = "",
    product_keyword: str = "",
    bill_order_bid: str = "",
    credit_order_kind: str = "",
    status: str = "",
    payment_provider: str = "",
    start_time: Any = "",
    end_time: Any = "",
    timezone_name: str | None = None,
) -> OperatorCreditOrdersPageDTO:
    """Return paginated operator-facing creator credit orders."""

    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    normalized_payment_provider = str(payment_provider or "").strip()
    status_code = _resolve_order_status_filter(status)
    product_type_filter = _resolve_credit_order_kind_filter(credit_order_kind)

    with app.app_context():
        query = BillingOrder.query.outerjoin(
            BillingProduct,
            BillingProduct.product_bid == BillingOrder.product_bid,
        ).filter(
            BillingOrder.deleted == 0,
        )

        if normalized_bill_order_bid:
            query = query.filter(
                BillingOrder.bill_order_bid == normalized_bill_order_bid
            )

        normalized_creator_keyword = str(creator_keyword or "").strip()
        if normalized_creator_keyword:
            matched_creator_bids = _load_matching_creator_bids_for_keyword(
                normalized_creator_keyword
            )
            if matched_creator_bids:
                query = query.filter(BillingOrder.creator_bid.in_(matched_creator_bids))
            else:
                query = query.filter(
                    BillingOrder.creator_bid == normalized_creator_keyword
                )

        normalized_product_keyword = str(product_keyword or "").strip()
        if normalized_product_keyword:
            matched_product_bids = _load_matching_credit_order_product_bids(
                normalized_product_keyword
            )
            if matched_product_bids:
                query = query.filter(BillingOrder.product_bid.in_(matched_product_bids))
            else:
                query = query.filter(BillingOrder.id == -1)

        if product_type_filter is not None:
            query = query.filter(BillingProduct.product_type == product_type_filter)

        if status_code is not None:
            query = query.filter(BillingOrder.status == status_code)

        if normalized_payment_provider:
            query = query.filter(
                BillingOrder.payment_provider == normalized_payment_provider
            )

        if start_time:
            query = query.filter(BillingOrder.created_at >= start_time)
        if end_time:
            query = query.filter(BillingOrder.created_at <= end_time)

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
            serializer=lambda row: row,
        )
        rows = list(payload.items)
        creator_map = _load_operator_creator_map(
            [str(row.creator_bid or "").strip() for row in rows]
        )
        product_map = _load_credit_order_product_map(
            [str(row.product_bid or "").strip() for row in rows]
        )
        grant_map = _load_credit_order_grant_map(
            app,
            [str(row.bill_order_bid or "").strip() for row in rows],
            timezone_name=timezone_name,
        )

        items = [
            _serialize_operator_credit_order(
                app,
                row,
                product=product_map.get(str(row.product_bid or "").strip()),
                creator=creator_map.get(str(row.creator_bid or "").strip(), {}),
                grant=grant_map.get(str(row.bill_order_bid or "").strip()),
                timezone_name=timezone_name,
            )
            for row in rows
        ]
        return OperatorCreditOrdersPageDTO(
            items=items,
            page=payload.page,
            page_count=payload.page_count,
            page_size=payload.page_size,
            total=payload.total,
        )


def get_operator_credit_order_detail(
    app: Flask,
    *,
    bill_order_bid: str,
    timezone_name: str | None = None,
) -> OperatorCreditOrderDetailDTO:
    """Return operator-facing creator credit order detail."""

    normalized_bill_order_bid = _normalize_bid(bill_order_bid)
    if not normalized_bill_order_bid:
        raise_param_error("bill_order_bid")

    with app.app_context():
        row = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.bill_order_bid == normalized_bill_order_bid,
            )
            .order_by(BillingOrder.id.desc())
            .first()
        )
        if row is None:
            raise_error("server.order.orderNotFound")

        creator_map = _load_operator_creator_map([str(row.creator_bid or "").strip()])
        product_map = _load_credit_order_product_map(
            [str(row.product_bid or "").strip()]
        )
        grant_map = _load_credit_order_grant_map(
            app,
            [normalized_bill_order_bid],
            timezone_name=timezone_name,
        )
        order = _serialize_operator_credit_order(
            app,
            row,
            product=product_map.get(str(row.product_bid or "").strip()),
            creator=creator_map.get(str(row.creator_bid or "").strip(), {}),
            grant=grant_map.get(normalized_bill_order_bid),
            timezone_name=timezone_name,
        )
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else None
        return OperatorCreditOrderDetailDTO(
            order=order,
            metadata=metadata,
            grant=grant_map.get(normalized_bill_order_bid),
        )


def build_admin_bill_daily_usage_metrics_page(
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


def build_admin_bill_daily_ledger_summary_page(
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
    bill_order_bid: str,
    *,
    timezone_name: str | None = None,
) -> BillingOrderDetailDTO:
    """Return a single billing order detail for the current creator."""

    normalized_creator_bid = _normalize_bid(creator_bid)
    normalized_order_bid = _normalize_bid(bill_order_bid)
    with app.app_context():
        row = (
            BillingOrder.query.filter(
                BillingOrder.deleted == 0,
                BillingOrder.creator_bid == normalized_creator_bid,
                BillingOrder.bill_order_bid == normalized_order_bid,
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


def build_admin_bill_domain_bindings(
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
