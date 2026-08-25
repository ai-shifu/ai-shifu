"""Publish and validate provider discounts for billing campaigns."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.service.common.models import raise_error, raise_param_error
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id

from .campaign_discount_providers import (
    CampaignDiscountProvider,
    ProviderDiscountCreateRequest,
    ProviderDiscountSnapshot,
    StripeCampaignDiscountProvider,
)
from .consts import (
    BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS,
    BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CREATING,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_LABELS,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH,
    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED,
    BILLING_PRODUCT_STATUS_ACTIVE,
    BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
)
from .models import (
    BillingCampaign,
    BillingCampaignProduct,
    BillingCampaignProviderDiscount,
    BillingProduct,
    BillingProductProviderPrice,
)
from .primitives import (
    credit_decimal_to_number,
    normalize_bid,
    normalize_json_object,
    to_decimal,
)
from .provider_price_mappings import (
    PROVIDER_STRIPE,
    ProviderPriceMappingError,
    resolve_current_stripe_provider_price_scope,
)


@dataclass(slots=True)
class CampaignProviderDiscountError(RuntimeError):
    """Represent a campaign provider discount failure."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Return the stable failure message."""
        return self.message


def serialize_campaign_provider_discount(
    row: BillingCampaignProviderDiscount,
) -> dict[str, Any]:
    """Serialize one provider discount row for admin surfaces."""
    metadata = normalize_json_object(row.metadata_json or {}).to_metadata_json()
    return {
        "campaign_provider_discount_bid": row.campaign_provider_discount_bid,
        "campaign_bid": row.campaign_bid,
        "product_bid": row.product_bid,
        "product_provider_price_bid": row.product_provider_price_bid,
        "provider": row.provider,
        "provider_account_id": row.provider_account_id,
        "provider_product_id": row.provider_product_id,
        "provider_price_id": row.provider_price_id,
        "provider_coupon_id": row.provider_coupon_id,
        "livemode": bool(row.livemode),
        "benefit_type": "discount",
        "discount_type": BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS.get(
            int(row.discount_type or 0), ""
        ),
        "list_price_amount": int(row.list_price_amount or 0),
        "campaign_price_amount": int(row.campaign_price_amount or 0),
        "discount_amount": int(row.discount_amount or 0),
        "discount_percent": credit_decimal_to_number(row.discount_percent or 0),
        "currency": row.currency,
        "duration": row.duration,
        "status": BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_LABELS.get(
            int(row.status or 0), "unknown"
        ),
        "validated_at": to_utc_iso(row.validated_at),
        "activated_at": to_utc_iso(row.activated_at),
        "retired_at": to_utc_iso(row.retired_at),
        "failure_code": row.failure_code,
        "failure_message": row.failure_message,
        "metadata": metadata,
    }


def summarize_campaign_provider_discounts(
    campaign_bids: list[str],
) -> dict[str, dict[str, Any]]:
    """Return provider discount counts by campaign for list pages."""
    if not campaign_bids:
        return {}
    rows = BillingCampaignProviderDiscount.query.filter(
        BillingCampaignProviderDiscount.deleted == 0,
        BillingCampaignProviderDiscount.campaign_bid.in_(campaign_bids),
    ).all()
    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        campaign_bid = str(row.campaign_bid or "")
        status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_LABELS.get(
            int(row.status or 0), "unknown"
        )
        summary = payload.setdefault(
            campaign_bid,
            {
                "total": 0,
                "active": 0,
                "failed": 0,
                "requires_republish": 0,
                "provider_invalid": 0,
                "cleanup_required": 0,
                "retired": 0,
                "latest_failure_code": "",
                "latest_failure_message": "",
            },
        )
        if status != "retired":
            summary["total"] += 1
        if status in summary:
            summary[status] += 1
        if row.failure_code or row.failure_message:
            summary["latest_failure_code"] = row.failure_code
            summary["latest_failure_message"] = row.failure_message
    return payload


def has_active_campaign_provider_discounts(campaign_bid: str) -> bool:
    """Return whether a campaign has active provider discounts."""
    normalized_campaign_bid = normalize_bid(campaign_bid)
    if not normalized_campaign_bid:
        return False
    return (
        BillingCampaignProviderDiscount.query.filter(
            BillingCampaignProviderDiscount.deleted == 0,
            BillingCampaignProviderDiscount.campaign_bid == normalized_campaign_bid,
            BillingCampaignProviderDiscount.status
            == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
        ).first()
        is not None
    )


def list_admin_campaign_provider_discounts(
    app: Flask,
    *,
    campaign_bid: str,
) -> dict[str, Any]:
    """Return provider discounts for one billing campaign."""
    normalized_campaign_bid = normalize_bid(campaign_bid)
    if not normalized_campaign_bid:
        raise_param_error("campaign_bid")
    with app_context_scope(app):
        _require_campaign(normalized_campaign_bid)
        rows = (
            BillingCampaignProviderDiscount.query.filter(
                BillingCampaignProviderDiscount.deleted == 0,
                BillingCampaignProviderDiscount.campaign_bid == normalized_campaign_bid,
            )
            .order_by(
                BillingCampaignProviderDiscount.product_bid.asc(),
                BillingCampaignProviderDiscount.id.asc(),
            )
            .all()
        )
        return {"items": [serialize_campaign_provider_discount(row) for row in rows]}


def mark_campaign_provider_discounts_requires_republish(
    *,
    product_provider_price_bid: str,
    reason: str,
) -> int:
    """Mark active discounts on an old provider price as needing republish."""
    normalized_bid = normalize_bid(product_provider_price_bid)
    if not normalized_bid:
        return 0
    rows = BillingCampaignProviderDiscount.query.filter(
        BillingCampaignProviderDiscount.deleted == 0,
        BillingCampaignProviderDiscount.product_provider_price_bid == normalized_bid,
        BillingCampaignProviderDiscount.status
        == BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
    ).all()
    now = now_utc()
    for row in rows:
        row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH
        row.failure_code = reason
        row.failure_message = "Provider price changed; republish this campaign"
        row.updated_at = now
        db.session.add(row)
    if rows:
        db.session.flush()
    return len(rows)


def publish_admin_campaign_provider_discounts(
    app: Flask,
    *,
    campaign_bid: str,
    operator_user_bid: str,
    provider: CampaignDiscountProvider | None = None,
) -> dict[str, Any]:
    """Publish Stripe coupons for discount campaign products."""
    normalized_campaign_bid = normalize_bid(campaign_bid)
    normalized_operator_bid = normalize_bid(operator_user_bid)
    if not normalized_campaign_bid:
        raise_param_error("campaign_bid")
    resolved_provider = provider or StripeCampaignDiscountProvider()

    with app_context_scope(app), unit_of_work():
        campaign = _require_campaign(normalized_campaign_bid)
        if int(campaign.benefit_type or 0) != BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT:
            return {"items": [], "summary": {"total": 0, "active": 0, "failed": 0}}
        bindings = _load_campaign_discount_bindings(normalized_campaign_bid)
        scope = resolve_current_stripe_provider_price_scope(app)
        rows = [
            _prepare_discount_row(
                app,
                campaign=campaign,
                binding=binding,
                scope_account_id=scope.provider_account_id,
                scope_livemode=scope.livemode,
                operator_user_bid=normalized_operator_bid,
            )
            for binding in bindings
        ]
        row_bids = [row.campaign_provider_discount_bid for row in rows]

    for row_bid in row_bids:
        _create_or_validate_provider_discount(
            app,
            row_bid=row_bid,
            operator_user_bid=normalized_operator_bid,
            provider=resolved_provider,
        )

    return list_admin_campaign_provider_discounts(
        app, campaign_bid=normalized_campaign_bid
    )


def validate_admin_campaign_provider_discount(
    app: Flask,
    *,
    campaign_provider_discount_bid: str,
    operator_user_bid: str,
    provider: CampaignDiscountProvider | None = None,
) -> dict[str, Any]:
    """Validate one persisted provider coupon against its locked rule."""
    normalized_bid = normalize_bid(campaign_provider_discount_bid)
    if not normalized_bid:
        raise_param_error("campaign_provider_discount_bid")
    resolved_provider = provider or StripeCampaignDiscountProvider()
    with app_context_scope(app), unit_of_work():
        row = _require_discount_row(normalized_bid)
        if not row.provider_coupon_id:
            code = "provider_coupon_missing"
            message = "Provider coupon is missing"
            raise _error(code, message, row)
        snapshot = resolved_provider.retrieve_campaign_discount(
            provider_coupon_id=row.provider_coupon_id,
            app=app,
        )
        _apply_validation_snapshot(row, snapshot, operator_user_bid=operator_user_bid)
        return serialize_campaign_provider_discount(row)


def retire_admin_campaign_provider_discounts(
    app: Flask,
    *,
    campaign_bid: str,
    operator_user_bid: str,
    provider: CampaignDiscountProvider | None = None,
) -> dict[str, Any]:
    """Retire all active provider discounts for a campaign."""
    normalized_campaign_bid = normalize_bid(campaign_bid)
    if not normalized_campaign_bid:
        raise_param_error("campaign_bid")
    resolved_provider = provider or StripeCampaignDiscountProvider()
    with app_context_scope(app):
        _require_campaign(normalized_campaign_bid)
        rows = BillingCampaignProviderDiscount.query.filter(
            BillingCampaignProviderDiscount.deleted == 0,
            BillingCampaignProviderDiscount.campaign_bid == normalized_campaign_bid,
            BillingCampaignProviderDiscount.status.in_(
                [
                    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE,
                    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID,
                    BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
                ]
            ),
        ).all()
        row_bids = [row.campaign_provider_discount_bid for row in rows]

    for row_bid in row_bids:
        _retire_provider_discount(
            app,
            row_bid=row_bid,
            operator_user_bid=operator_user_bid,
            provider=resolved_provider,
        )
    return list_admin_campaign_provider_discounts(
        app, campaign_bid=normalized_campaign_bid
    )


def _prepare_discount_row(
    app: Flask,
    *,
    campaign: BillingCampaign,
    binding: BillingCampaignProduct,
    scope_account_id: str,
    scope_livemode: bool,
    operator_user_bid: str,
) -> BillingCampaignProviderDiscount:
    product = _require_product(binding.product_bid)
    mapping = _require_active_provider_price_mapping(
        product_bid=product.product_bid,
        provider_account_id=scope_account_id,
        livemode=scope_livemode,
    )
    list_price_amount = int(mapping.unit_amount or 0)
    campaign_price_amount = int(binding.campaign_price_amount or 0)
    discount_type = int(binding.discount_type or 0)
    if discount_type == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED:
        if campaign_price_amount <= 0 or campaign_price_amount >= list_price_amount:
            code = "invalid_fixed_discount"
            message = "Fixed campaign price must be lower than the provider price"
            raise _error(code, message, binding)
        discount_amount = list_price_amount - campaign_price_amount
        discount_percent = Decimal(0)
    elif discount_type == BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT:
        discount_percent = to_decimal(binding.discount_percent).quantize(
            Decimal("0.01")
        )
        if discount_percent <= 0 or discount_percent > 100:
            code = "invalid_percent_discount"
            message = "Invalid percent discount"
            raise _error(code, message, binding)
        discount_amount = 0
        percent_discount_amount = int(
            (Decimal(list_price_amount) * discount_percent / Decimal(100)).quantize(
                Decimal(1)
            )
        )
        campaign_price_amount = max(list_price_amount - percent_discount_amount, 0)
    else:
        code = "invalid_discount_type"
        message = "Unsupported campaign discount type"
        raise _error(code, message, binding)

    row = _load_discount_row(
        campaign_bid=campaign.campaign_bid,
        product_bid=product.product_bid,
        product_provider_price_bid=mapping.provider_price_bid,
        provider=PROVIDER_STRIPE,
        provider_account_id=mapping.provider_account_id,
    )
    now = now_utc()
    replaces_discount_bid = ""
    if row is not None and _should_create_replacement_row(row):
        replaces_discount_bid = str(row.campaign_provider_discount_bid or "")
        row = None
    if row is None:
        row = BillingCampaignProviderDiscount(
            campaign_provider_discount_bid=generate_id(app),
            campaign_bid=campaign.campaign_bid,
            product_bid=product.product_bid,
            product_provider_price_bid=mapping.provider_price_bid,
            provider=PROVIDER_STRIPE,
            created_user_bid=operator_user_bid,
            replaces_discount_bid=replaces_discount_bid,
        )
    row.provider_account_id = mapping.provider_account_id
    row.provider_product_id = mapping.provider_product_id
    row.provider_price_id = mapping.provider_price_id
    row.livemode = int(bool(mapping.livemode))
    row.benefit_type = BILLING_CAMPAIGN_BENEFIT_TYPE_DISCOUNT
    row.discount_type = discount_type
    row.list_price_amount = list_price_amount
    row.campaign_price_amount = campaign_price_amount
    row.discount_amount = discount_amount
    row.discount_percent = discount_percent
    row.currency = str(mapping.currency or "").strip().upper()
    row.duration = "once"
    if int(row.status or 0) != BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE:
        row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CREATING
    row.failure_code = ""
    row.failure_message = ""
    row.updated_user_bid = operator_user_bid
    row.updated_at = now
    row.metadata_json = _discount_metadata(row, campaign=campaign, product=product)
    db.session.add(row)
    db.session.flush()
    return row


def _create_or_validate_provider_discount(
    app: Flask,
    *,
    row_bid: str,
    operator_user_bid: str,
    provider: CampaignDiscountProvider,
) -> None:
    with app_context_scope(app), unit_of_work():
        row = _require_discount_row(row_bid)
        product = _require_product(row.product_bid)
        if row.provider_coupon_id:
            snapshot = provider.retrieve_campaign_discount(
                provider_coupon_id=row.provider_coupon_id,
                app=app,
            )
        else:
            try:
                snapshot = provider.create_campaign_discount(
                    request=ProviderDiscountCreateRequest(
                        campaign_bid=row.campaign_bid,
                        campaign_provider_discount_bid=(
                            row.campaign_provider_discount_bid
                        ),
                        product_bid=row.product_bid,
                        product_code=product.product_code,
                        product_provider_price_bid=row.product_provider_price_bid,
                        provider_product_id=row.provider_product_id,
                        provider_price_id=row.provider_price_id,
                        currency=row.currency,
                        amount_off=(
                            int(row.discount_amount or 0)
                            if int(row.discount_type or 0)
                            == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED
                            else None
                        ),
                        percent_off=(
                            to_decimal(row.discount_percent)
                            if int(row.discount_type or 0)
                            == BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT
                            else None
                        ),
                        duration=row.duration,
                        metadata={
                            str(k): str(v)
                            for k, v in _discount_metadata(row, product=product).items()
                        },
                        idempotency_key=_discount_idempotency_key(row),
                    ),
                    app=app,
                )
            except Exception as exc:
                row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED
                row.failure_code = "provider_create_failed"
                row.failure_message = _sanitize_error_message(exc)
                row.updated_user_bid = operator_user_bid
                row.updated_at = now_utc()
                db.session.add(row)
                return
        _apply_validation_snapshot(row, snapshot, operator_user_bid=operator_user_bid)


def _retire_provider_discount(
    app: Flask,
    *,
    row_bid: str,
    operator_user_bid: str,
    provider: CampaignDiscountProvider,
) -> None:
    with app_context_scope(app), unit_of_work():
        row = _require_discount_row(row_bid)
        now = now_utc()
        if row.provider_coupon_id:
            try:
                provider.retire_campaign_discount(
                    provider_coupon_id=row.provider_coupon_id,
                    app=app,
                )
            except Exception as exc:
                row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED
                row.failure_code = "provider_retire_failed"
                row.failure_message = _sanitize_error_message(exc)
                row.updated_user_bid = operator_user_bid
                row.updated_at = now
                db.session.add(row)
                return
        row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED
        row.retired_at = now
        row.failure_code = ""
        row.failure_message = ""
        row.updated_user_bid = operator_user_bid
        row.updated_at = now
        db.session.add(row)


def _apply_validation_snapshot(
    row: BillingCampaignProviderDiscount,
    snapshot: ProviderDiscountSnapshot,
    *,
    operator_user_bid: str,
) -> None:
    now = now_utc()
    row.provider_coupon_id = snapshot.provider_coupon_id or row.provider_coupon_id
    row.validated_at = now
    row.updated_user_bid = normalize_bid(operator_user_bid)
    row.updated_at = now
    validation_error = _validate_snapshot(row, snapshot)
    if validation_error:
        row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID
        row.failure_code = validation_error["code"]
        row.failure_message = validation_error["message"]
    else:
        row.status = BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_ACTIVE
        row.activated_at = row.activated_at or now
        row.failure_code = ""
        row.failure_message = ""
    row.metadata_json = {
        **normalize_json_object(row.metadata_json or {}).to_metadata_json(),
        "provider_snapshot": {
            "provider_coupon_id": snapshot.provider_coupon_id,
            "valid": snapshot.valid,
            "currency": snapshot.currency,
            "amount_off": snapshot.amount_off,
            "percent_off": str(snapshot.percent_off)
            if snapshot.percent_off is not None
            else None,
            "duration": snapshot.duration,
        },
    }
    db.session.add(row)


def _validate_snapshot(
    row: BillingCampaignProviderDiscount,
    snapshot: ProviderDiscountSnapshot,
) -> dict[str, str] | None:
    if not snapshot.provider_coupon_id:
        return {
            "code": "provider_coupon_missing",
            "message": "Provider coupon is missing",
        }
    if not snapshot.valid:
        return {
            "code": "provider_coupon_invalid",
            "message": "Provider coupon is not valid",
        }
    if snapshot.livemode is not None and bool(snapshot.livemode) != bool(row.livemode):
        return {
            "code": "livemode_mismatch",
            "message": "Provider coupon mode does not match",
        }
    if str(snapshot.duration or "") != "once":
        return {
            "code": "duration_mismatch",
            "message": "Provider coupon duration does not match",
        }
    if int(row.discount_type or 0) == BILLING_CAMPAIGN_DISCOUNT_TYPE_FIXED:
        if int(snapshot.amount_off or 0) != int(row.discount_amount or 0):
            return {
                "code": "amount_off_mismatch",
                "message": "Provider coupon amount does not match",
            }
        if str(snapshot.currency or "").upper() != str(row.currency or "").upper():
            return {
                "code": "currency_mismatch",
                "message": "Provider coupon currency does not match",
            }
    snapshot_percent = to_decimal(snapshot.percent_off or 0).quantize(Decimal("0.01"))
    row_percent = to_decimal(row.discount_percent).quantize(Decimal("0.01"))
    if (
        int(row.discount_type or 0) == BILLING_CAMPAIGN_DISCOUNT_TYPE_PERCENT
        and snapshot_percent != row_percent
    ):
        return {
            "code": "percent_off_mismatch",
            "message": "Provider coupon percent does not match",
        }
    return None


def _discount_metadata(
    row: BillingCampaignProviderDiscount,
    *,
    campaign: BillingCampaign | None = None,
    product: BillingProduct | None = None,
) -> dict[str, object]:
    return {
        "campaign_bid": row.campaign_bid,
        "campaign_provider_discount_bid": row.campaign_provider_discount_bid,
        "product_bid": row.product_bid,
        "product_code": product.product_code if product is not None else "",
        "product_provider_price_bid": row.product_provider_price_bid,
        "provider_price_id": row.provider_price_id,
        "benefit_type": "discount",
        "discount_type": BILLING_CAMPAIGN_DISCOUNT_TYPE_LABELS.get(
            int(row.discount_type or 0), ""
        ),
        "duration": "once",
        "campaign_name": campaign.name if campaign is not None else "",
    }


def _discount_idempotency_key(row: BillingCampaignProviderDiscount) -> str:
    return (
        "billing-campaign-provider-discount:"
        f"{row.campaign_provider_discount_bid}:create:v1"
    )


def _load_campaign_discount_bindings(campaign_bid: str) -> list[BillingCampaignProduct]:
    rows = (
        BillingCampaignProduct.query.filter(
            BillingCampaignProduct.deleted == 0,
            BillingCampaignProduct.campaign_bid == campaign_bid,
        )
        .order_by(BillingCampaignProduct.id.asc())
        .all()
    )
    if not rows:
        raise_param_error("products")
    return rows


def _require_campaign(campaign_bid: str) -> BillingCampaign:
    row = BillingCampaign.query.filter(
        BillingCampaign.deleted == 0,
        BillingCampaign.campaign_bid == campaign_bid,
    ).first()
    if row is None:
        raise_error("server.billing.campaignNotFound")
    return row


def _require_product(product_bid: str) -> BillingProduct:
    row = BillingProduct.query.filter(
        BillingProduct.deleted == 0,
        BillingProduct.status == BILLING_PRODUCT_STATUS_ACTIVE,
        BillingProduct.product_bid == normalize_bid(product_bid),
    ).first()
    if row is None:
        raise_param_error("product_bid")
    return row


def _require_active_provider_price_mapping(
    *,
    product_bid: str,
    provider_account_id: str,
    livemode: bool,
) -> BillingProductProviderPrice:
    row = (
        BillingProductProviderPrice.query.filter(
            BillingProductProviderPrice.deleted == 0,
            BillingProductProviderPrice.product_bid == normalize_bid(product_bid),
            BillingProductProviderPrice.provider == PROVIDER_STRIPE,
            BillingProductProviderPrice.provider_account_id
            == normalize_bid(provider_account_id),
            BillingProductProviderPrice.livemode == int(bool(livemode)),
            BillingProductProviderPrice.status == BILLING_PROVIDER_PRICE_STATUS_ACTIVE,
        )
        .order_by(BillingProductProviderPrice.id.asc())
        .first()
    )
    if row is None:
        code = "active_provider_price_missing"
        message = (
            "Active provider price mapping is required before publishing "
            "campaign discounts"
        )
        raise ProviderPriceMappingError(code, message, {"product_bid": product_bid})
    return row


def _load_discount_row(
    *,
    campaign_bid: str,
    product_bid: str,
    product_provider_price_bid: str,
    provider: str,
    provider_account_id: str,
) -> BillingCampaignProviderDiscount | None:
    return (
        BillingCampaignProviderDiscount.query.filter(
            BillingCampaignProviderDiscount.deleted == 0,
            BillingCampaignProviderDiscount.campaign_bid == normalize_bid(campaign_bid),
            BillingCampaignProviderDiscount.product_bid == normalize_bid(product_bid),
            BillingCampaignProviderDiscount.product_provider_price_bid
            == normalize_bid(product_provider_price_bid),
            BillingCampaignProviderDiscount.provider
            == str(provider or "").strip().lower(),
            BillingCampaignProviderDiscount.provider_account_id
            == normalize_bid(provider_account_id),
        )
        .order_by(BillingCampaignProviderDiscount.id.desc())
        .first()
    )


def _should_create_replacement_row(row: BillingCampaignProviderDiscount) -> bool:
    if not row.provider_coupon_id:
        return False
    return int(row.status or 0) in {
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_CLEANUP_REQUIRED,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_FAILED,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_PROVIDER_INVALID,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_REQUIRES_REPUBLISH,
        BILLING_CAMPAIGN_PROVIDER_DISCOUNT_STATUS_RETIRED,
    }


def _require_discount_row(row_bid: str) -> BillingCampaignProviderDiscount:
    row = BillingCampaignProviderDiscount.query.filter(
        BillingCampaignProviderDiscount.deleted == 0,
        BillingCampaignProviderDiscount.campaign_provider_discount_bid
        == normalize_bid(row_bid),
    ).first()
    if row is None:
        code = "campaign_provider_discount_not_found"
        message = "Campaign provider discount was not found"
        raise _error(code, message, {"campaign_provider_discount_bid": row_bid})
    return row


def _error(code: str, message: str, subject: object) -> CampaignProviderDiscountError:
    details = {}
    for attr in ("campaign_bid", "product_bid", "campaign_provider_discount_bid"):
        value = (
            getattr(subject, attr, "")
            if not isinstance(subject, dict)
            else subject.get(attr, "")
        )
        if value:
            details[attr] = value
    return CampaignProviderDiscountError(code, message, details)


def _sanitize_error_message(exc: Exception) -> str:
    return (
        str(exc).replace("sk_live_", "sk_****_").replace("sk_test_", "sk_****_")[:500]
    )
