"""Shared lookup helpers for billing read models."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from flaskr.dao import db
from flaskr.i18n import get_current_language, set_language
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.util.datetime import (
    parse_naive_utc,
)
from sqlalchemy import or_

from .consts import (
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
    CREDIT_LEDGER_ENTRY_TYPE_GRANT,
    CREDIT_SOURCE_TYPE_LABELS,
    CREDIT_SOURCE_TYPE_USAGE,
)
from .models import (
    BillingProduct,
    CreditLedgerEntry,
)
from .primitives import credit_decimal_to_number
from .primitives import normalize_bid as _normalize_bid
from .primitives import normalize_json_object as _normalize_json_object
from .serializers import (
    serialize_operator_credit_order_grant as _serialize_operator_credit_order_grant,
)

if TYPE_CHECKING:
    from datetime import datetime
    from types import ModuleType

    from flask import Flask
    from flask_sqlalchemy.query import Query

    from .dtos import (
        OperatorCreditOrderGrantDTO,
    )


def _read_models_facade() -> ModuleType:
    """Resolve collaborators through ``read_models`` so its patch points stay live."""
    from . import read_models

    return read_models


_OPERATOR_PRODUCT_FILTER_LANGUAGES = (
    "zh-CN",
    "en-US",
    "de-DE",
    "es-ES",
    "fr-FR",
    "ar-SA",
    "th-TH",
    "ur-PK",
)
_ADMIN_BILLING_FOCUS_ATTENTION_REASON_ORDER = (
    "rapid_growth",
    "high_consumption",
    "high_frequency",
    "active_production",
    "debug_preview_heavy",
    "sustained_activity",
)


def _filter_out_reserved_credit_grant_ledgers(query: Query) -> Query:
    bucket_credit_state_expr = db.func.lower(
        db.func.trim(
            db.func.coalesce(
                CreditLedgerEntry.metadata_json["bucket_credit_state"].as_string(),
                "",
            )
        )
    )
    return query.filter(bucket_credit_state_expr.notin_(("reserved", "absorbed")))


def _parse_stat_date(value: str) -> datetime.date | None:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        return None
    try:
        return parse_naive_utc(normalized_value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _sort_admin_billing_focus_attention_reasons(
    reasons: set[str],
) -> list[str]:
    return [
        reason
        for reason in _ADMIN_BILLING_FOCUS_ATTENTION_REASON_ORDER
        if reason in reasons
    ]


def _is_public_trial_catalog_product(row: BillingProduct) -> bool:
    if str(row.product_code or "").strip() == BILLING_TRIAL_PRODUCT_CODE:
        return True
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return bool(metadata.get(BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG))


def _load_translated_product_name_map(
    products: list[BillingProduct],
) -> dict[str, list[str]]:
    display_name_keys = {
        str(product.display_name_i18n_key or "").strip()
        for product in products
        if str(product.display_name_i18n_key or "").strip()
    }
    if not display_name_keys:
        return {}

    translated_name_map: dict[str, list[str]] = {
        display_name_key: [] for display_name_key in display_name_keys
    }
    original_language = get_current_language()
    try:
        for language in _OPERATOR_PRODUCT_FILTER_LANGUAGES:
            set_language(language)
            for display_name_key in display_name_keys:
                translated_name = str(
                    _read_models_facade().translate(display_name_key) or ""
                ).strip()
                if (
                    translated_name
                    and translated_name != display_name_key
                    and translated_name not in translated_name_map[display_name_key]
                ):
                    translated_name_map[display_name_key].append(translated_name)
    finally:
        set_language(original_language)

    return translated_name_map


def _load_matching_credit_order_product_bids(keyword: str) -> list[str]:
    normalized_keyword = str(keyword or "").strip().lower()
    if not normalized_keyword:
        return []

    structural_match_pattern = f"%{normalized_keyword}%"
    structurally_matched_products = (
        BillingProduct.query.filter(
            or_(
                BillingProduct.product_bid.ilike(structural_match_pattern),
                BillingProduct.product_code.ilike(structural_match_pattern),
                BillingProduct.display_name_i18n_key.ilike(structural_match_pattern),
            )
        )
        .order_by(BillingProduct.id.desc())
        .all()
    )
    matched_product_bids = [
        normalized_product_bid
        for product in structurally_matched_products
        if (normalized_product_bid := str(product.product_bid or "").strip())
    ]
    if matched_product_bids:
        return matched_product_bids

    numeric_match_bids = _load_numeric_credit_order_product_bids(normalized_keyword)
    if numeric_match_bids:
        return numeric_match_bids

    translated_name_candidates = (
        BillingProduct.query.filter(BillingProduct.display_name_i18n_key != "")
        .order_by(BillingProduct.id.desc())
        .all()
    )
    translated_name_map = _load_translated_product_name_map(translated_name_candidates)
    translated_match_bids: list[str] = []
    for product in translated_name_candidates:
        display_name_key = str(product.display_name_i18n_key or "").strip()
        translated_names = translated_name_map.get(display_name_key, [])
        if any(normalized_keyword in term.lower() for term in translated_names):
            normalized_product_bid = str(product.product_bid or "").strip()
            if normalized_product_bid:
                translated_match_bids.append(normalized_product_bid)
    return translated_match_bids


def _load_numeric_credit_order_product_bids(keyword: str) -> list[str]:
    normalized_keyword = str(keyword or "").strip().replace(",", "")
    if not normalized_keyword:
        return []

    try:
        numeric_value = Decimal(normalized_keyword)
    except (InvalidOperation, ValueError):
        return []
    if not numeric_value.is_finite():
        return []

    filters = [BillingProduct.credit_amount == numeric_value]
    price_amount_candidates: set[int] = set()
    if numeric_value >= 0:
        if numeric_value == numeric_value.to_integral_value():
            price_amount_candidates.add(int(numeric_value))
        price_amount_minor = numeric_value * Decimal(100)
        if price_amount_minor == price_amount_minor.to_integral_value():
            price_amount_candidates.add(int(price_amount_minor))
    if price_amount_candidates:
        filters.append(BillingProduct.price_amount.in_(sorted(price_amount_candidates)))

    rows = (
        BillingProduct.query.filter(or_(*filters))
        .order_by(BillingProduct.id.desc())
        .all()
    )
    return [
        normalized_product_bid
        for product in rows
        if (normalized_product_bid := str(product.product_bid or "").strip())
    ]


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
) -> dict[str, OperatorCreditOrderGrantDTO]:
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
    payload: dict[str, OperatorCreditOrderGrantDTO] = {}
    for row in rows:
        source_bid = str(row.source_bid or "").strip()
        if not source_bid or source_bid in payload:
            continue
        source_type_label = CREDIT_SOURCE_TYPE_LABELS.get(int(row.source_type or 0), "")
        payload[source_bid] = _serialize_operator_credit_order_grant(
            app,
            source_type=source_type_label,
            source_bid=source_bid,
            granted_credits=credit_decimal_to_number(row.amount),
            valid_from=row.consumable_from,
            valid_to=row.expires_at,
        )
    return payload


def _load_matching_creator_bids_for_keyword(keyword: str) -> list[str]:
    normalized = str(keyword or "").strip()
    if not normalized:
        return []

    matched_bids: set[str] = set()

    users = UserEntity.query.filter(
        UserEntity.deleted == 0,
        UserEntity.user_identify == normalized,
    ).yield_per(200)
    for user in users:
        user_bid = str(user.user_bid or "").strip()
        if user_bid:
            matched_bids.add(user_bid)

    credentials = AuthCredential.query.filter(
        AuthCredential.deleted == 0,
        AuthCredential.provider_name.in_(["phone", "email"]),
        AuthCredential.identifier == normalized,
    ).yield_per(200)
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
) -> dict[str, dict[str, object]]:
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
