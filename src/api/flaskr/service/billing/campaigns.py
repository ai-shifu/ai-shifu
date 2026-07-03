"""Billing campaign read/write helpers for admin and catalog surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from flask import Flask
from sqlalchemy import func

from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.common.models import (
    raise_error,
    raise_error_with_args,
    raise_param_error,
)
from flaskr.util.datetime import now_utc
from flaskr.util.uuid import generate_id

from .consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_BENEFIT_TYPE_LABELS,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
    BILLING_ORDER_STATUS_PAID,
    BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PRODUCT_TYPE_LABELS,
    BILLING_PRODUCT_TYPE_PLAN,
    BILLING_PRODUCT_TYPE_TOPUP,
    BILLING_TRIAL_PRODUCT_CODE,
    BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG,
)
from .dtos import (
    AdminBillingCampaignDetailDTO,
    AdminBillingCampaignProductOptionsDTO,
    AdminBillingCampaignsPageDTO,
)
from .models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingOrder,
    BillingProduct,
)
from .primitives import (
    coerce_datetime,
    credit_decimal_to_number,
    normalize_bid,
    quantize_credit_amount,
    to_decimal,
)
from .queries import normalize_pagination
from .serializers import (
    serialize_admin_campaign,
    serialize_admin_campaign_detail,
    serialize_admin_campaign_product_option,
)


@dataclass(slots=True, frozen=True)
class AppliedBillingCampaignResult:
    campaign_bid: str = ""
    benefit_type_code: int = 0
    discount_type_code: int = 0
    discount_amount: int = 0
    discount_percent: Decimal = Decimal("0")
    campaign_price_amount: int = 0
    bonus_credit_amount: Decimal = Decimal("0")

    def to_catalog_payload(self) -> dict[str, Any]:
        if not self.campaign_bid:
            return {}
        payload: dict[str, Any] = {
            "campaign_bid": self.campaign_bid,
            "benefit_type": BILLING_CAMPAIGN_BENEFIT_TYPE_LABELS.get(
                self.benefit_type_code,
                "",
            ),
            "campaign_price_amount": int(self.campaign_price_amount or 0),
            "discount_amount": int(self.discount_amount or 0),
            "bonus_credit_amount": credit_decimal_to_number(
                self.bonus_credit_amount or 0
            ),
        }
        if self.discount_type_code:
            payload["discount_type"] = BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS.get(
                self.discount_type_code,
                "",
            )
            payload["discount_percent"] = credit_decimal_to_number(
                self.discount_percent or 0,
                precision=2,
            )
        return payload


@dataclass(slots=True, frozen=True)
class NormalizedCampaignProductConfig:
    product_bid: str
    product_type: int
    benefit_type_code: int
    discount_type_code: int = 0
    discount_amount: int = 0
    discount_percent: Decimal = Decimal("0")
    campaign_price_amount: int = 0
    bonus_credit_amount: Decimal = Decimal("0")


def build_admin_billing_campaign_product_options(
    app: Flask,
) -> AdminBillingCampaignProductOptionsDTO:
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
        plans = []
        topups = []
        for row in rows:
            metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            if str(row.product_code or "").strip() == BILLING_TRIAL_PRODUCT_CODE:
                continue
            if bool(metadata.get(BILLING_TRIAL_PRODUCT_METADATA_PUBLIC_FLAG)):
                continue
            payload = serialize_admin_campaign_product_option(row)
            if row.product_type == BILLING_PRODUCT_TYPE_PLAN:
                plans.append(payload)
            elif row.product_type == BILLING_PRODUCT_TYPE_TOPUP:
                topups.append(payload)
        return AdminBillingCampaignProductOptionsDTO(plans=plans, topups=topups)


def build_admin_billing_campaigns_page(
    app: Flask,
    *,
    page_index: int = 1,
    page_size: int = 20,
    keyword: str = "",
    product_type: str = "",
    benefit_type: str = "",
    status: str = "",
    start_time: str = "",
    end_time: str = "",
) -> AdminBillingCampaignsPageDTO:
    safe_page_index, safe_page_size = normalize_pagination(page_index, page_size)
    normalized_keyword = str(keyword or "").strip()
    normalized_status = str(status or "").strip().lower()
    product_type_code = _resolve_product_type_filter(product_type)
    benefit_type_code = _resolve_benefit_type(benefit_type, required=False)
    start_at = _coerce_required_datetime(
        start_time, required=False, parameter_name="start_time"
    )
    end_at = _coerce_required_datetime(
        end_time, required=False, parameter_name="end_time"
    )

    with app.app_context():
        query = BillingCampaign.query.filter(BillingCampaign.deleted == 0)
        if normalized_keyword:
            like_value = f"%{normalized_keyword}%"
            query = query.filter(BillingCampaign.name.ilike(like_value))
        if benefit_type_code is not None:
            query = query.filter(BillingCampaign.benefit_type == benefit_type_code)
        if start_at is not None:
            query = query.filter(BillingCampaign.end_at >= start_at)
        if end_at is not None:
            query = query.filter(BillingCampaign.start_at <= end_at)
        if product_type_code is not None:
            query = query.filter(
                BillingCampaign.campaign_bid.in_(
                    db.session.query(BillingCampaignProduct.campaign_bid).filter(
                        BillingCampaignProduct.deleted == 0,
                        BillingCampaignProduct.product_type == product_type_code,
                    )
                )
            )

        if normalized_status:
            now = now_utc()
            if normalized_status == "active":
                query = query.filter(
                    BillingCampaign.enabled == 1,
                    BillingCampaign.start_at <= now,
                    BillingCampaign.end_at > now,
                )
            elif normalized_status == "upcoming":
                query = query.filter(
                    BillingCampaign.enabled == 1,
                    BillingCampaign.start_at > now,
                )
            elif normalized_status == "ended":
                query = query.filter(BillingCampaign.end_at <= now)
            elif normalized_status == "inactive":
                query = query.filter(BillingCampaign.enabled == 0)
            else:
                raise_param_error("status")

        query = query.order_by(
            BillingCampaign.updated_at.desc(),
            BillingCampaign.id.desc(),
        )

        total = query.order_by(None).count()
        if total == 0:
            return AdminBillingCampaignsPageDTO(
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
        campaign_bids = [str(row.campaign_bid or "") for row in rows]
        product_name_map = _load_campaign_product_name_map(campaign_bids=campaign_bids)
        product_type_map = _load_campaign_product_type_map(campaign_bids=campaign_bids)
        binding_map = _load_campaign_binding_map(campaign_bids=campaign_bids)
        hit_count_map = _load_campaign_hit_count_map(campaign_bids=campaign_bids)
        return AdminBillingCampaignsPageDTO(
            items=[
                _serialize_admin_campaign_row(
                    app,
                    row,
                    product_names=product_name_map.get(row.campaign_bid, []),
                    product_types=product_type_map.get(row.campaign_bid, []),
                    bindings=binding_map.get(row.campaign_bid, []),
                    hit_order_count=hit_count_map.get(row.campaign_bid, 0),
                )
                for row in rows
            ],
            page=resolved_page,
            page_count=page_count,
            page_size=safe_page_size,
            total=total,
        )


def build_admin_billing_campaign_detail(
    app: Flask,
    campaign_bid: str,
) -> AdminBillingCampaignDetailDTO:
    normalized_campaign_bid = normalize_bid(campaign_bid)
    if not normalized_campaign_bid:
        raise_param_error("campaign_bid")

    with app.app_context():
        row = _load_campaign(normalized_campaign_bid)
        if row is None:
            raise_error("server.billing.campaignNotFound")
        product_rows = _load_campaign_products(normalized_campaign_bid)
        binding_map = _load_campaign_binding_map(
            campaign_bids=[normalized_campaign_bid]
        )
        bindings = binding_map.get(normalized_campaign_bid, [])
        binding_by_product_bid = {binding.product_bid: binding for binding in bindings}
        hit_count_map = _load_campaign_hit_count_map(
            campaign_bids=[normalized_campaign_bid]
        )
        product_names = [product.display_name_i18n_key for product in product_rows]
        product_types = sorted(
            {
                BILLING_PRODUCT_TYPE_LABELS.get(product.product_type, "")
                for product in product_rows
                if BILLING_PRODUCT_TYPE_LABELS.get(product.product_type, "")
            }
        )
        campaign_dto = _serialize_admin_campaign_row(
            app,
            row,
            product_names=product_names,
            product_types=product_types,
            bindings=bindings,
            hit_order_count=hit_count_map.get(normalized_campaign_bid, 0),
        )
        return serialize_admin_campaign_detail(
            campaign_dto,
            products=[
                serialize_admin_campaign_product_option(
                    product,
                    binding=binding_by_product_bid.get(product.product_bid),
                )
                for product in product_rows
            ],
            created_user_bid=str(row.created_user_bid or ""),
            updated_user_bid=str(row.updated_user_bid or ""),
        )


def create_admin_billing_campaign(
    app: Flask,
    *,
    operator_user_bid: str,
    payload: dict[str, Any],
) -> AdminBillingCampaignDetailDTO:
    normalized_operator_bid = normalize_bid(operator_user_bid)
    draft = _normalize_campaign_payload(payload)
    with app.app_context():
        product_configs = _load_campaign_target_product_configs(draft["products"])
        campaign_rule_snapshot = _resolve_campaign_rule_snapshot(product_configs)
        _validate_campaign_overlap(
            product_bids=sorted(config.product_bid for config in product_configs),
            enabled=draft["enabled"],
            start_at=draft["start_at"],
            end_at=draft["end_at"],
        )

        row = BillingCampaign(
            campaign_bid=generate_id(app),
            name=draft["name"],
            note=draft["note"],
            benefit_type=draft["benefit_type_code"],
            discount_type=campaign_rule_snapshot["discount_type_code"],
            discount_amount=campaign_rule_snapshot["discount_amount"],
            discount_percent=campaign_rule_snapshot["discount_percent"],
            bonus_credit_amount=campaign_rule_snapshot["bonus_credit_amount"],
            enabled=1 if draft["enabled"] else 0,
            start_at=draft["start_at"],
            end_at=draft["end_at"],
            created_user_bid=normalized_operator_bid,
            updated_user_bid=normalized_operator_bid,
        )
        db.session.add(row)
        db.session.flush()
        _replace_campaign_products(row.campaign_bid, product_configs)
        db.session.commit()
        return build_admin_billing_campaign_detail(
            app,
            row.campaign_bid,
        )


def update_admin_billing_campaign(
    app: Flask,
    *,
    operator_user_bid: str,
    campaign_bid: str,
    payload: dict[str, Any],
) -> AdminBillingCampaignDetailDTO:
    normalized_operator_bid = normalize_bid(operator_user_bid)
    normalized_campaign_bid = normalize_bid(campaign_bid)
    if not normalized_campaign_bid:
        raise_param_error("campaign_bid")
    draft = _normalize_campaign_payload(payload)

    with app.app_context():
        row = _load_campaign(normalized_campaign_bid)
        if row is None:
            raise_error("server.billing.campaignNotFound")
        product_configs = _load_campaign_target_product_configs(draft["products"])
        campaign_rule_snapshot = _resolve_campaign_rule_snapshot(product_configs)
        hit_order_count = _load_campaign_hit_count_map(
            campaign_bids=[normalized_campaign_bid]
        ).get(
            normalized_campaign_bid,
            0,
        )
        if hit_order_count > 0:
            _assert_campaign_products_unchanged_after_hit(
                row,
                next_product_configs=product_configs,
            )

        _validate_campaign_overlap(
            product_bids=sorted(config.product_bid for config in product_configs),
            enabled=draft["enabled"],
            start_at=draft["start_at"],
            end_at=draft["end_at"],
            exclude_campaign_bid=normalized_campaign_bid,
        )
        row.name = draft["name"]
        row.note = draft["note"]
        row.benefit_type = draft["benefit_type_code"]
        row.discount_type = campaign_rule_snapshot["discount_type_code"]
        row.discount_amount = campaign_rule_snapshot["discount_amount"]
        row.discount_percent = campaign_rule_snapshot["discount_percent"]
        row.bonus_credit_amount = campaign_rule_snapshot["bonus_credit_amount"]
        row.enabled = 1 if draft["enabled"] else 0
        row.start_at = draft["start_at"]
        row.end_at = draft["end_at"]
        row.updated_user_bid = normalized_operator_bid
        row.updated_at = now_utc()
        db.session.add(row)
        if hit_order_count <= 0:
            _replace_campaign_products(normalized_campaign_bid, product_configs)
        db.session.commit()
        return build_admin_billing_campaign_detail(app, normalized_campaign_bid)


def update_admin_billing_campaign_status(
    app: Flask,
    *,
    operator_user_bid: str,
    campaign_bid: str,
    payload: dict[str, Any],
) -> AdminBillingCampaignDetailDTO:
    normalized_operator_bid = normalize_bid(operator_user_bid)
    normalized_campaign_bid = normalize_bid(campaign_bid)
    if not normalized_campaign_bid:
        raise_param_error("campaign_bid")
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise_param_error("enabled")

    with app.app_context():
        row = _load_campaign(normalized_campaign_bid)
        if row is None:
            raise_error("server.billing.campaignNotFound")
        product_bids = sorted(
            product.product_bid
            for product in _load_campaign_products(normalized_campaign_bid)
        )
        _validate_campaign_overlap(
            product_bids=product_bids,
            enabled=enabled,
            start_at=row.start_at,
            end_at=row.end_at,
            exclude_campaign_bid=normalized_campaign_bid,
        )
        row.enabled = 1 if enabled else 0
        row.updated_user_bid = normalized_operator_bid
        row.updated_at = now_utc()
        db.session.add(row)
        db.session.commit()
        return build_admin_billing_campaign_detail(app, normalized_campaign_bid)


def resolve_catalog_campaign_payload(
    product: BillingProduct,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    return resolve_applied_billing_campaign(
        product,
        as_of=as_of,
    ).to_catalog_payload()


def resolve_applied_billing_campaign(
    product: BillingProduct,
    *,
    order_type: int | None = None,
    as_of: datetime | None = None,
) -> AppliedBillingCampaignResult:
    if order_type == BILLING_ORDER_TYPE_SUBSCRIPTION_RENEWAL:
        return AppliedBillingCampaignResult()
    active_binding = _load_active_campaign_binding_for_product(
        product.product_bid,
        as_of=as_of,
    )
    if active_binding is None:
        return AppliedBillingCampaignResult()
    campaign, binding = active_binding
    return _resolve_applied_campaign_result(
        product=product,
        campaign=campaign,
        binding=binding,
    )


def _normalize_campaign_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    note = str(payload.get("note") or "").strip()
    if not name:
        raise_param_error("name")
    if len(name) > 255:
        raise_param_error("name")
    if len(note) > 500:
        raise_param_error("note")

    benefit_type_code = _resolve_benefit_type(
        payload.get("benefit_type"), required=True
    )
    start_at = _coerce_required_datetime(
        payload.get("start_at"), required=True, parameter_name="start_at"
    )
    end_at = _coerce_required_datetime(
        payload.get("end_at"), required=True, parameter_name="end_at"
    )
    if start_at is None or end_at is None or end_at <= start_at:
        raise_param_error("end_at")

    enabled_raw = payload.get("enabled")
    enabled = True if enabled_raw is None else bool(enabled_raw)
    product_drafts = _normalize_campaign_product_drafts(
        payload,
        benefit_type_code=benefit_type_code,
    )

    return {
        "name": name,
        "note": note,
        "benefit_type_code": benefit_type_code,
        "start_at": start_at,
        "end_at": end_at,
        "products": product_drafts,
        "enabled": enabled,
    }


def _normalize_campaign_product_drafts(
    payload: dict[str, Any],
    *,
    benefit_type_code: int,
) -> list[dict[str, Any]]:
    raw_products = payload.get("products")
    if isinstance(raw_products, list):
        product_drafts = []
        for raw_product in raw_products:
            if not isinstance(raw_product, dict):
                raise_param_error("products")
            normalized_product_bid = normalize_bid(raw_product.get("product_bid"))
            if not normalized_product_bid:
                raise_param_error("products")
            if benefit_type_code == BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT:
                discount_type_code = _resolve_discount_type(
                    raw_product.get("discount_type"),
                    required=True,
                )
                discount_percent = Decimal("0")
                campaign_price_amount = 0
                if discount_type_code == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED:
                    campaign_price_amount = _coerce_campaign_price_amount(
                        raw_product.get("campaign_price_amount")
                    )
                else:
                    discount_percent = _coerce_discount_percent(
                        raw_product.get("discount_percent")
                    )
                product_drafts.append(
                    {
                        "product_bid": normalized_product_bid,
                        "discount_type_code": discount_type_code,
                        "discount_percent": discount_percent,
                        "campaign_price_amount": campaign_price_amount,
                        "bonus_credit_amount": Decimal("0"),
                    }
                )
            else:
                product_drafts.append(
                    {
                        "product_bid": normalized_product_bid,
                        "discount_type_code": 0,
                        "discount_percent": Decimal("0"),
                        "campaign_price_amount": 0,
                        "bonus_credit_amount": _coerce_bonus_credit_amount(
                            raw_product.get("bonus_credit_amount")
                        ),
                    }
                )
        return _dedupe_campaign_product_drafts(product_drafts)

    product_bids_value = payload.get("product_bids")
    if not isinstance(product_bids_value, list):
        raise_param_error("product_bids")
    product_bids = [
        normalized_bid
        for item in product_bids_value
        if (normalized_bid := normalize_bid(item))
    ]
    if not product_bids:
        raise_param_error("product_bids")

    if benefit_type_code == BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT:
        discount_type_code = _resolve_discount_type(
            payload.get("discount_type"),
            required=True,
        )
        discount_percent = Decimal("0")
        campaign_price_amount = 0
        if discount_type_code == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED:
            discount_amount = _coerce_discount_amount(payload.get("discount_amount"))
        else:
            discount_amount = 0
            discount_percent = _coerce_discount_percent(payload.get("discount_percent"))
        return _dedupe_campaign_product_drafts(
            [
                {
                    "product_bid": product_bid,
                    "discount_type_code": discount_type_code,
                    "discount_amount": discount_amount,
                    "discount_percent": discount_percent,
                    "campaign_price_amount": campaign_price_amount,
                    "bonus_credit_amount": Decimal("0"),
                }
                for product_bid in product_bids
            ]
        )

    bonus_credit_amount = _coerce_bonus_credit_amount(
        payload.get("bonus_credit_amount")
    )
    return _dedupe_campaign_product_drafts(
        [
            {
                "product_bid": product_bid,
                "discount_type_code": 0,
                "discount_amount": 0,
                "discount_percent": Decimal("0"),
                "campaign_price_amount": 0,
                "bonus_credit_amount": bonus_credit_amount,
            }
            for product_bid in product_bids
        ]
    )


def _dedupe_campaign_product_drafts(
    product_drafts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for draft in product_drafts:
        deduped[str(draft.get("product_bid") or "")] = draft
    ordered = [
        deduped[product_bid]
        for product_bid in sorted(product_bid for product_bid in deduped if product_bid)
    ]
    if not ordered:
        raise_param_error("products")
    return ordered


def _coerce_discount_amount(value: Any) -> int:
    try:
        discount_amount = max(int(value or 0), 0)
    except (TypeError, ValueError):
        raise_param_error("discount_amount")
    if discount_amount <= 0:
        raise_param_error("discount_amount")
    return discount_amount


def _coerce_discount_percent(value: Any) -> Decimal:
    try:
        discount_percent = to_decimal(value)
    except Exception:
        raise_param_error("discount_percent")
    if discount_percent <= 0 or discount_percent > 100:
        raise_param_error("discount_percent")
    return discount_percent.quantize(Decimal("0.01"))


def _coerce_campaign_price_amount(value: Any) -> int:
    try:
        campaign_price_amount = int(value or 0)
    except (TypeError, ValueError):
        raise_param_error("campaign_price_amount")
    if campaign_price_amount <= 0:
        raise_param_error("campaign_price_amount")
    return campaign_price_amount


def _coerce_bonus_credit_amount(value: Any) -> Decimal:
    try:
        bonus_credit_amount = quantize_credit_amount(value)
    except Exception:
        raise_param_error("bonus_credit_amount")
    if bonus_credit_amount <= 0:
        raise_param_error("bonus_credit_amount")
    return bonus_credit_amount


def _coerce_required_datetime(
    value: Any,
    *,
    required: bool,
    parameter_name: str,
) -> datetime | None:
    parsed = coerce_datetime(value)
    if parsed is None and required:
        raise_param_error(parameter_name)
    return parsed


def _resolve_product_type_filter(value: Any) -> int | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    for code, label in BILLING_PRODUCT_TYPE_LABELS.items():
        if label == normalized and code in {
            BILLING_PRODUCT_TYPE_PLAN,
            BILLING_PRODUCT_TYPE_TOPUP,
        }:
            return code
    raise_param_error("product_type")


def _resolve_benefit_type(value: Any, *, required: bool) -> int | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        if required:
            raise_param_error("benefit_type")
        return None
    for code, label in BILLING_CAMPAIGN_BENEFIT_TYPE_LABELS.items():
        if label == normalized:
            return code
    raise_param_error("benefit_type")


def _resolve_discount_type(value: Any, *, required: bool) -> int | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        if required:
            raise_param_error("discount_type")
        return None
    for code, label in BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS.items():
        if label == normalized:
            return code
    raise_param_error("discount_type")


def _load_campaign(campaign_bid: str) -> BillingCampaign | None:
    return (
        BillingCampaign.query.filter(
            BillingCampaign.deleted == 0,
            BillingCampaign.campaign_bid == normalize_bid(campaign_bid),
        )
        .order_by(BillingCampaign.id.desc())
        .first()
    )


def _load_campaign_products(campaign_bid: str) -> list[BillingProduct]:
    return (
        BillingProduct.query.join(
            BillingCampaignProduct,
            BillingCampaignProduct.product_bid == BillingProduct.product_bid,
        )
        .filter(
            BillingCampaignProduct.deleted == 0,
            BillingCampaignProduct.campaign_bid == normalize_bid(campaign_bid),
            BillingProduct.deleted == 0,
        )
        .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
        .all()
    )


def _load_campaign_target_products(product_bids: list[str]) -> list[BillingProduct]:
    rows = (
        BillingProduct.query.filter(
            BillingProduct.deleted == 0,
            BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
            BillingProduct.product_bid.in_(product_bids),
        )
        .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
        .all()
    )
    if len(rows) != len(product_bids):
        raise_param_error("product_bids")
    return rows


def _validate_campaign_product_targets(products: list[BillingProduct]) -> None:
    if not products:
        raise_param_error("product_bids")
    for product in products:
        if product.product_type not in {
            BILLING_PRODUCT_TYPE_PLAN,
            BILLING_PRODUCT_TYPE_TOPUP,
        }:
            raise_param_error("product_bids")


def _load_campaign_target_product_configs(
    product_drafts: list[dict[str, Any]],
) -> list[NormalizedCampaignProductConfig]:
    product_bids = sorted(
        {
            normalize_bid(draft.get("product_bid"))
            for draft in product_drafts
            if normalize_bid(draft.get("product_bid"))
        }
    )
    products = _load_campaign_target_products(product_bids)
    _validate_campaign_product_targets(products)
    product_map = {product.product_bid: product for product in products}
    configs: list[NormalizedCampaignProductConfig] = []
    for draft in product_drafts:
        product_bid = normalize_bid(draft.get("product_bid"))
        product = product_map.get(product_bid)
        if product is None:
            raise_param_error("products")
        if (
            int(draft.get("discount_type_code") or 0)
            == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED
        ):
            legacy_discount_amount = int(draft.get("discount_amount") or 0)
            if legacy_discount_amount > 0:
                campaign_price_amount = max(
                    int(product.price_amount or 0) - legacy_discount_amount, 0
                )
            else:
                campaign_price_amount = int(draft.get("campaign_price_amount") or 0)
            if campaign_price_amount <= 0 or campaign_price_amount >= int(
                product.price_amount or 0
            ):
                raise_param_error("campaign_price_amount")
            discount_amount = max(
                int(product.price_amount or 0) - campaign_price_amount, 0
            )
            configs.append(
                NormalizedCampaignProductConfig(
                    product_bid=product.product_bid,
                    product_type=int(product.product_type or 0),
                    benefit_type_code=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                    discount_type_code=BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
                    discount_amount=discount_amount,
                    discount_percent=Decimal("0"),
                    campaign_price_amount=campaign_price_amount,
                    bonus_credit_amount=Decimal("0"),
                )
            )
            continue
        if (
            int(draft.get("discount_type_code") or 0)
            == BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT
        ):
            percent_value = _coerce_discount_percent(draft.get("discount_percent"))
            discount_amount = int(
                (
                    Decimal(int(product.price_amount or 0))
                    * percent_value
                    / Decimal("100")
                ).quantize(Decimal("1"))
            )
            campaign_price_amount = max(
                int(product.price_amount or 0) - discount_amount, 0
            )
            configs.append(
                NormalizedCampaignProductConfig(
                    product_bid=product.product_bid,
                    product_type=int(product.product_type or 0),
                    benefit_type_code=BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
                    discount_type_code=BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
                    discount_amount=discount_amount,
                    discount_percent=percent_value,
                    campaign_price_amount=campaign_price_amount,
                    bonus_credit_amount=Decimal("0"),
                )
            )
            continue
        bonus_credit_amount = _coerce_bonus_credit_amount(
            draft.get("bonus_credit_amount")
        )
        configs.append(
            NormalizedCampaignProductConfig(
                product_bid=product.product_bid,
                product_type=int(product.product_type or 0),
                benefit_type_code=BILLING_CAMPAIGN_BENEFIT_TYPE_BONUS,
                bonus_credit_amount=bonus_credit_amount,
                campaign_price_amount=int(product.price_amount or 0),
            )
        )
    if not configs:
        raise_param_error("products")
    return configs


def _assert_campaign_products_unchanged_after_hit(
    row: BillingCampaign,
    *,
    next_product_configs: list[NormalizedCampaignProductConfig],
) -> None:
    """Prevent rule drift after orders have already captured campaign pricing."""
    if int(row.benefit_type or 0) not in {
        config.benefit_type_code for config in next_product_configs
    }:
        raise_error("server.billing.campaignLockedAfterHit")

    existing_bindings = _load_campaign_binding_map(
        campaign_bids=[str(row.campaign_bid or "")]
    ).get(str(row.campaign_bid or ""), [])
    existing_by_product_bid = {
        str(binding.product_bid or ""): binding for binding in existing_bindings
    }
    next_by_product_bid = {
        config.product_bid: config for config in next_product_configs
    }
    if sorted(existing_by_product_bid) != sorted(next_by_product_bid):
        raise_error("server.billing.campaignLockedAfterHit")

    for product_bid, next_config in next_by_product_bid.items():
        existing = existing_by_product_bid.get(product_bid)
        if existing is None:
            raise_error("server.billing.campaignLockedAfterHit")
        if (
            int(existing.product_type or 0) != next_config.product_type
            or int(existing.discount_type or 0) != next_config.discount_type_code
            or int(existing.discount_amount or 0) != next_config.discount_amount
            or to_decimal(existing.discount_percent) != next_config.discount_percent
            or int(existing.campaign_price_amount or 0)
            != next_config.campaign_price_amount
            or quantize_credit_amount(existing.bonus_credit_amount)
            != next_config.bonus_credit_amount
        ):
            raise_error("server.billing.campaignLockedAfterHit")


def _replace_campaign_products(
    campaign_bid: str,
    product_configs: list[NormalizedCampaignProductConfig],
) -> None:
    BillingCampaignProduct.query.filter(
        BillingCampaignProduct.campaign_bid == normalize_bid(campaign_bid),
        BillingCampaignProduct.deleted == 0,
    ).delete(synchronize_session=False)
    for product_config in product_configs:
        db.session.add(
            BillingCampaignProduct(
                campaign_bid=normalize_bid(campaign_bid),
                product_bid=product_config.product_bid,
                product_type=product_config.product_type,
                discount_type=product_config.discount_type_code,
                discount_amount=product_config.discount_amount,
                discount_percent=product_config.discount_percent,
                campaign_price_amount=product_config.campaign_price_amount,
                bonus_credit_amount=product_config.bonus_credit_amount,
            )
        )


def _validate_campaign_overlap(
    *,
    product_bids: list[str],
    enabled: bool,
    start_at: datetime,
    end_at: datetime,
    exclude_campaign_bid: str = "",
) -> None:
    if not enabled or not product_bids:
        return
    now = now_utc()
    query = BillingCampaign.query.join(
        BillingCampaignProduct,
        BillingCampaignProduct.campaign_bid == BillingCampaign.campaign_bid,
    ).filter(
        BillingCampaign.deleted == 0,
        BillingCampaign.enabled == 1,
        BillingCampaignProduct.deleted == 0,
        BillingCampaignProduct.product_bid.in_(product_bids),
        BillingCampaign.end_at > now,
        BillingCampaign.start_at < end_at,
        BillingCampaign.end_at > start_at,
    )
    normalized_exclude = normalize_bid(exclude_campaign_bid)
    if normalized_exclude:
        query = query.filter(BillingCampaign.campaign_bid != normalized_exclude)
    if query.first() is not None:
        overlapping_product_names = _load_campaign_overlap_product_names(
            product_bids=product_bids,
            start_at=start_at,
            end_at=end_at,
            exclude_campaign_bid=normalized_exclude,
        )
        raise_error_with_args(
            "server.billing.campaignOverlapActive",
            product_names=", ".join(overlapping_product_names)
            if overlapping_product_names
            else "",
        )


def _load_campaign_overlap_product_names(
    *,
    product_bids: list[str],
    start_at: datetime,
    end_at: datetime,
    exclude_campaign_bid: str = "",
) -> list[str]:
    if not product_bids:
        return []
    now = now_utc()
    query = (
        db.session.query(BillingProduct.display_name_i18n_key)
        .join(
            BillingCampaignProduct,
            BillingCampaignProduct.product_bid == BillingProduct.product_bid,
        )
        .join(
            BillingCampaign,
            BillingCampaign.campaign_bid == BillingCampaignProduct.campaign_bid,
        )
        .filter(
            BillingProduct.deleted == 0,
            BillingCampaignProduct.deleted == 0,
            BillingCampaign.deleted == 0,
            BillingCampaign.enabled == 1,
            BillingCampaignProduct.product_bid.in_(product_bids),
            BillingCampaign.end_at > now,
            BillingCampaign.start_at < end_at,
            BillingCampaign.end_at > start_at,
        )
        .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
    )
    normalized_exclude = normalize_bid(exclude_campaign_bid)
    if normalized_exclude:
        query = query.filter(BillingCampaign.campaign_bid != normalized_exclude)
    names: list[str] = []
    seen_names: set[str] = set()
    for (display_name_i18n_key,) in query.all():
        translated_name = str(_(str(display_name_i18n_key or "")) or "").strip()
        if translated_name and translated_name not in seen_names:
            seen_names.add(translated_name)
            names.append(translated_name)
    return names


def _load_campaign_product_name_map(
    *,
    campaign_bids: list[str] | None = None,
) -> dict[str, list[str]]:
    query = (
        db.session.query(
            BillingCampaignProduct.campaign_bid,
            BillingProduct.display_name_i18n_key,
        )
        .join(
            BillingProduct,
            BillingProduct.product_bid == BillingCampaignProduct.product_bid,
        )
        .filter(
            BillingCampaignProduct.deleted == 0,
            BillingProduct.deleted == 0,
        )
        .order_by(BillingProduct.sort_order.asc(), BillingProduct.id.asc())
    )
    if campaign_bids:
        query = query.filter(BillingCampaignProduct.campaign_bid.in_(campaign_bids))
    rows = query.all()
    payload: dict[str, list[str]] = {}
    for campaign_bid, display_name in rows:
        payload.setdefault(str(campaign_bid or ""), []).append(str(display_name or ""))
    return payload


def _load_campaign_product_type_map(
    *,
    campaign_bids: list[str] | None = None,
) -> dict[str, list[str]]:
    query = db.session.query(
        BillingCampaignProduct.campaign_bid,
        BillingCampaignProduct.product_type,
    ).filter(BillingCampaignProduct.deleted == 0)
    if campaign_bids:
        query = query.filter(BillingCampaignProduct.campaign_bid.in_(campaign_bids))
    rows = query.all()
    payload: dict[str, set[str]] = {}
    for campaign_bid, product_type in rows:
        label = BILLING_PRODUCT_TYPE_LABELS.get(int(product_type or 0), "")
        if not label:
            continue
        payload.setdefault(str(campaign_bid or ""), set()).add(label)
    return {campaign_bid: sorted(labels) for campaign_bid, labels in payload.items()}


def _load_campaign_binding_map(
    *,
    campaign_bids: list[str] | None = None,
) -> dict[str, list[BillingCampaignProduct]]:
    query = BillingCampaignProduct.query.filter(BillingCampaignProduct.deleted == 0)
    if campaign_bids:
        query = query.filter(BillingCampaignProduct.campaign_bid.in_(campaign_bids))
    rows = query.order_by(
        BillingCampaignProduct.campaign_bid.asc(),
        BillingCampaignProduct.id.asc(),
    ).all()
    payload: dict[str, list[BillingCampaignProduct]] = {}
    for row in rows:
        payload.setdefault(str(row.campaign_bid or ""), []).append(row)
    return payload


def _serialize_admin_campaign_row(
    app: Flask,
    row: BillingCampaign,
    *,
    product_names: list[str],
    product_types: list[str],
    bindings: list[BillingCampaignProduct],
    hit_order_count: int,
):
    campaign_rule_snapshot = _resolve_campaign_rule_snapshot_from_bindings(
        row,
        bindings=bindings,
    )
    return serialize_admin_campaign(
        app,
        row,
        product_names=product_names,
        product_types=product_types,
        hit_order_count=hit_order_count,
        has_custom_product_rules=campaign_rule_snapshot["has_custom_product_rules"],
        discount_type_code=campaign_rule_snapshot["discount_type_code"],
        discount_amount=campaign_rule_snapshot["discount_amount"],
        discount_percent=campaign_rule_snapshot["discount_percent"],
        bonus_credit_amount=campaign_rule_snapshot["bonus_credit_amount"],
    )


def _resolve_campaign_rule_snapshot(
    product_configs: list[NormalizedCampaignProductConfig],
) -> dict[str, Any]:
    if not product_configs:
        return {
            "discount_type_code": 0,
            "discount_amount": 0,
            "discount_percent": Decimal("0"),
            "bonus_credit_amount": Decimal("0"),
            "has_custom_product_rules": False,
        }
    first = product_configs[0]
    has_custom_product_rules = any(
        config.discount_type_code != first.discount_type_code
        or config.discount_amount != first.discount_amount
        or config.discount_percent != first.discount_percent
        or config.bonus_credit_amount != first.bonus_credit_amount
        or config.campaign_price_amount != first.campaign_price_amount
        for config in product_configs[1:]
    )
    return {
        "discount_type_code": first.discount_type_code,
        "discount_amount": first.discount_amount,
        "discount_percent": first.discount_percent,
        "bonus_credit_amount": first.bonus_credit_amount,
        "has_custom_product_rules": has_custom_product_rules,
    }


def _resolve_campaign_rule_snapshot_from_bindings(
    row: BillingCampaign,
    *,
    bindings: list[BillingCampaignProduct],
) -> dict[str, Any]:
    if not bindings:
        return {
            "discount_type_code": int(row.discount_type or 0),
            "discount_amount": int(row.discount_amount or 0),
            "discount_percent": to_decimal(row.discount_percent),
            "bonus_credit_amount": quantize_credit_amount(row.bonus_credit_amount),
            "has_custom_product_rules": False,
        }
    first = bindings[0]
    has_custom_product_rules = any(
        int(binding.discount_type or 0) != int(first.discount_type or 0)
        or int(binding.discount_amount or 0) != int(first.discount_amount or 0)
        or to_decimal(binding.discount_percent) != to_decimal(first.discount_percent)
        or quantize_credit_amount(binding.bonus_credit_amount)
        != quantize_credit_amount(first.bonus_credit_amount)
        or int(binding.campaign_price_amount or 0)
        != int(first.campaign_price_amount or 0)
        for binding in bindings[1:]
    )
    return {
        "discount_type_code": int(first.discount_type or 0),
        "discount_amount": int(first.discount_amount or 0),
        "discount_percent": to_decimal(first.discount_percent),
        "bonus_credit_amount": quantize_credit_amount(first.bonus_credit_amount),
        "has_custom_product_rules": has_custom_product_rules,
    }


def _load_campaign_hit_count_map(
    *,
    campaign_bids: list[str] | None = None,
) -> dict[str, int]:
    if campaign_bids is not None and not campaign_bids:
        return {}
    query = db.session.query(
        BillingOrder.campaign_bid,
        func.count(BillingOrder.id),
    ).filter(
        BillingOrder.deleted == 0,
        BillingOrder.campaign_bid != "",
        BillingOrder.status == BILLING_ORDER_STATUS_PAID,
    )
    if campaign_bids:
        query = query.filter(BillingOrder.campaign_bid.in_(campaign_bids))
    rows = query.group_by(BillingOrder.campaign_bid).all()
    return {str(campaign_bid or ""): int(count or 0) for campaign_bid, count in rows}


def _resolve_applied_campaign_result(
    *,
    product: BillingProduct,
    campaign: BillingCampaign,
    binding: BillingCampaignProduct | None = None,
) -> AppliedBillingCampaignResult:
    resolved_discount_type_code = int(
        getattr(binding, "discount_type", 0) or campaign.discount_type or 0
    )
    discount_type_code = int(resolved_discount_type_code)
    discount_amount = int(
        getattr(binding, "discount_amount", 0) or campaign.discount_amount or 0
    )
    discount_percent_source = campaign.discount_percent
    if binding is not None and resolved_discount_type_code == int(
        getattr(binding, "discount_type", 0) or 0
    ):
        discount_percent_source = getattr(binding, "discount_percent", 0)
    discount_percent = to_decimal(discount_percent_source)
    campaign_price_amount = int(getattr(binding, "campaign_price_amount", 0) or 0)
    bonus_credit_amount_source = campaign.bonus_credit_amount
    if (
        binding is not None
        and quantize_credit_amount(getattr(binding, "bonus_credit_amount", 0) or 0) > 0
    ):
        bonus_credit_amount_source = getattr(binding, "bonus_credit_amount", 0)
    bonus_credit_amount = quantize_credit_amount(bonus_credit_amount_source)

    if campaign.benefit_type == BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT:
        if discount_type_code == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED:
            if campaign_price_amount <= 0 and discount_amount > 0:
                campaign_price_amount = max(
                    int(product.price_amount or 0) - discount_amount,
                    0,
                )
            if discount_amount <= 0 and campaign_price_amount >= 0:
                discount_amount = max(
                    int(product.price_amount or 0) - campaign_price_amount,
                    0,
                )
            return AppliedBillingCampaignResult(
                campaign_bid=campaign.campaign_bid,
                benefit_type_code=campaign.benefit_type,
                discount_type_code=discount_type_code,
                discount_amount=discount_amount,
                discount_percent=discount_percent,
                campaign_price_amount=max(campaign_price_amount, 0),
            )
        percent_value = max(min(discount_percent, Decimal("100")), Decimal("0"))
        if discount_amount <= 0:
            discount_amount = int(
                (
                    Decimal(int(product.price_amount or 0))
                    * percent_value
                    / Decimal("100")
                ).quantize(Decimal("1"))
            )
        if campaign_price_amount <= 0 and int(product.price_amount or 0) > 0:
            campaign_price_amount = max(
                int(product.price_amount or 0) - discount_amount, 0
            )
        return AppliedBillingCampaignResult(
            campaign_bid=campaign.campaign_bid,
            benefit_type_code=campaign.benefit_type,
            discount_type_code=discount_type_code,
            discount_amount=discount_amount,
            discount_percent=percent_value,
            campaign_price_amount=campaign_price_amount,
        )

    return AppliedBillingCampaignResult(
        campaign_bid=campaign.campaign_bid,
        benefit_type_code=campaign.benefit_type,
        campaign_price_amount=int(product.price_amount or 0),
        bonus_credit_amount=bonus_credit_amount,
    )


def _load_active_campaign_binding_for_product(
    product_bid: str,
    *,
    as_of: datetime | None = None,
) -> tuple[BillingCampaign, BillingCampaignProduct | None] | None:
    now = as_of or now_utc()
    normalized_product_bid = normalize_bid(product_bid)
    if not normalized_product_bid:
        return None
    row = (
        db.session.query(BillingCampaign, BillingCampaignProduct)
        .join(
            BillingCampaignProduct,
            BillingCampaignProduct.campaign_bid == BillingCampaign.campaign_bid,
        )
        .filter(
            BillingCampaign.deleted == 0,
            BillingCampaign.enabled == 1,
            BillingCampaign.start_at <= now,
            BillingCampaign.end_at > now,
            BillingCampaignProduct.deleted == 0,
            BillingCampaignProduct.product_bid == normalized_product_bid,
        )
        .order_by(BillingCampaign.updated_at.desc(), BillingCampaign.id.desc())
        .first()
    )
    if row is None:
        return None
    return row[0], row[1]
